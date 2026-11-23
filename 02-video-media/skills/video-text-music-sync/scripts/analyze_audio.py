#!/usr/bin/env python3
"""Local acoustic candidates; never claims lyric, downbeat or listening verification."""
import argparse
import array
import csv
import json
import math
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
from fractions import Fraction


def ensure_output(path):
    path = Path(path).expanduser().absolute()
    path.mkdir(parents=True, exist_ok=True)
    if not os.access(path, os.W_OK):
        raise ValueError('输出目录不可写。')
    return path


def frame_at(seconds, fps):
    value = Fraction(str(seconds)) * fps
    return (2 * value.numerator + value.denominator) // (2 * value.denominator)


def percentile(values, q):
    if not values:
        return 0.0
    values = sorted(values)
    return values[min(len(values) - 1, int((len(values) - 1) * q))]


def analyze(samples, sr, fps, bpm=None, anchor=None):
    hop = sr // 100  # 10ms; envelope uses two hops, time-stamped at its centre.
    size = 2 * hop
    envelope, levels = [], []
    for start in range(0, len(samples) - size + 1, hop):
        part = samples[start:start + size]
        rms = math.sqrt(sum(x*x for x in part) / size) / 32768
        diff = math.sqrt(sum((part[i] - part[i-1])**2 for i in range(1, size)) / (size-1)) / 65536
        levels.append(rms)
        envelope.append(rms + diff)
    duration = len(samples) / sr
    flux = [0.0] + [max(0.0, envelope[i] - envelope[i-1]) for i in range(1, len(envelope))]
    median = statistics.median(flux) if flux else 0.0
    mad = statistics.median(abs(x - median) for x in flux) if flux else 0.0
    threshold = max(median + 2*mad, percentile(flux, .75), 1e-5)
    peaks = []
    for i in range(1, len(flux)-1):
        if flux[i] > threshold and flux[i] >= flux[i-1] and flux[i] > flux[i+1]:
            if peaks and (i-peaks[-1]) * hop / sr < .08:
                if flux[i] > flux[peaks[-1]]:
                    peaks[-1] = i
            else:
                peaks.append(i)
    maximum = max(flux, default=0.0)
    onsets = [{'time_seconds': round((i*hop + size/2)/sr, 6),
               'frame': frame_at((i*hop + size/2)/sr, fps),
               'strength': round(flux[i]/maximum, 4), 'status': 'acoustic_candidate'} for i in peaks]

    # Autocorrelation is deliberately a candidate list, not a musical judgement.
    scores = []
    if duration >= 4 and max(levels, default=0) > 1e-4:
        for lag in range(33, min(101, len(flux)//2)):
            a, b = flux[lag:], flux[:-lag]
            denom = math.sqrt(sum(x*x for x in a) * sum(x*x for x in b))
            score = sum(x*y for x,y in zip(a,b)) / denom if denom else 0
            if score > .08:
                scores.append((score, 60*sr/(hop*lag)))
    scores.sort(reverse=True)
    candidates = []
    for score, tempo in scores:
        if all(abs(tempo - item['bpm']) > 3 for item in candidates):
            candidates.append({'bpm': round(tempo, 3), 'periodicity_score': round(score, 4),
                               'status': 'acoustic_candidate'})
        if len(candidates) == 4:
            break
    grid = []
    selected_bpm = bpm or (candidates[0]['bpm'] if candidates else None)
    phase = anchor
    if selected_bpm:
        period = 60 / selected_bpm
        if phase is None and onsets:
            weighted = sorted(onsets, key=lambda x: x['strength'], reverse=True)[:100]
            def phase_score(test):
                total = 0
                for event in onsets:
                    distance = abs(((event['time_seconds']-test + period/2) % period)-period/2)
                    total += event['strength'] * max(0, 1-distance/.07)
                return total
            phase = max((item['time_seconds'] % period for item in weighted), key=phase_score)
        if phase is not None:
            # Absolute positions, no repeated frame rounding / frame accumulation.
            k = math.ceil(-phase/period)
            while phase + k*period < duration:
                t = phase + k*period
                if t >= 0:
                    grid.append({'time_seconds': round(t, 6), 'frame': frame_at(t, fps),
                                 'status': 'user_parameter_candidate' if bpm else 'acoustic_candidate'})
                k += 1
    rms_blocks = []
    for i in range(0, len(levels), 100):
        part = levels[i:i+100]
        rms_blocks.append({'time_seconds': round(i*hop/sr, 3),
                           'rms_dbfs': round(20*math.log10(max(1e-12, math.sqrt(sum(x*x for x in part)/len(part)))), 2)})
    return {'duration_seconds': duration, 'onsets': onsets, 'bpm_candidates': candidates,
            'grid_bpm': selected_bpm, 'grid_anchor_seconds': phase, 'beat_grid_candidates': grid,
            'level_blocks': rms_blocks,
            'limitations': ['未进行听感辨识或歌词识别', '瞬态不等于鼓点；拍速可能为半速或倍速',
                            '网格相位未确认小节第一拍；混合讲解音轨不适合全段共用BPM',
                            '候选须按实际音乐和文字复核，网格可为空']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True)
    parser.add_argument('--out-dir', required=True)
    parser.add_argument('--start', type=float, default=0)
    parser.add_argument('--duration', type=float)
    parser.add_argument('--fps', default='60000/1001')
    parser.add_argument('--bpm', type=float)
    parser.add_argument('--anchor', type=float, help='Seconds relative to selected audio segment')
    parser.add_argument('--ffmpeg', default=shutil.which('ffmpeg'))
    args = parser.parse_args()
    fps = Fraction(args.fps)
    numbers = [args.start, fps.numerator/fps.denominator]
    numbers += [x for x in (args.duration,args.bpm,args.anchor) if x is not None]
    if not all(math.isfinite(x) for x in numbers) or args.start < 0 or fps <= 0:
        parser.error('参数必须有限，start >= 0，fps > 0。')
    if args.duration is not None and args.duration <= 0:
        parser.error('duration必须 > 0。')
    if args.bpm is not None and not 20 <= args.bpm <= 400:
        parser.error('bpm必须在20–400之间。')
    if args.anchor is not None and args.bpm is None:
        parser.error('指定anchor时也须指定bpm。')
    if not args.ffmpeg:
        parser.error('未发现FFmpeg，请指定--ffmpeg。')
    source = Path(args.input).expanduser().resolve(strict=True)
    command = [args.ffmpeg, '-v', 'error', '-ss', str(args.start), '-i', str(source)]
    if args.duration is not None:
        command += ['-t', str(args.duration)]
    command += ['-map', '0:a:0', '-vn', '-ac', '1', '-ar', '16000', '-f', 's16le', 'pipe:1']
    process = subprocess.run(command, capture_output=True)
    if process.returncode:
        raise ValueError('音轨读取失败：'+process.stderr.decode(errors='replace')[-1500:])
    samples = array.array('h')
    samples.frombytes(process.stdout)
    if sys.byteorder != 'little':
        samples.byteswap()
    if len(samples) < 320:
        raise ValueError('所选音频不足20ms或区间超出源文件。')
    data = analyze(samples, 16000, fps, args.bpm, args.anchor)
    data.update(schema_version=1, source=str(source), source_start_seconds=args.start,
                fps=str(fps), timing_origin='selected_segment_start', verification='not_listened_or_verified')
    out = ensure_output(args.out_dir)
    (out/'analysis.json').write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    with (out/'candidates.csv').open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.writer(stream)
        writer.writerow(['kind','segment_seconds','source_seconds','segment_frame','strength','status'])
        for kind, items in [('onset',data['onsets']),('beat_grid',data['beat_grid_candidates'])]:
            for item in items:
                writer.writerow([kind,item['time_seconds'],round(args.start+item['time_seconds'],6),
                                 item['frame'],item.get('strength',''),item['status']])
    print(json.dumps({'output':str(out), 'duration':data['duration_seconds'],
                      'onsets':len(data['onsets']), 'bpm_candidates':data['bpm_candidates'],
                      'verification':data['verification']}, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, ZeroDivisionError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(2)
