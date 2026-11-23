#!/usr/bin/env python3
"""Validate a frame-based text timeline and emit editable AE setup JSX, without launching AE."""
import argparse
import csv
from fractions import Fraction
import json
import math
from pathlib import Path
import sys
sys.dont_write_bytecode = True
from analyze_audio import ensure_output


def validate(data):
    fps = Fraction(str(data['fps']))
    if fps <= 0 or fps > 240:
        raise ValueError('fps必须 > 0 且 <= 240。')
    for key in ('width','height','duration_frames'):
        if type(data.get(key)) is not int or data[key] <= 0:
            raise ValueError(key+'须为正整数。')
    if not isinstance(data.get('name'), str) or not data['name'].strip():
        raise ValueError('需要非空name。')
    total = data['duration_frames']
    for row in data.get('texts', []):
        if not isinstance(row.get('text'),str) or not row['text'].strip():
            raise ValueError('文字不可为空。')
        start, end = row.get('start_frame'), row.get('end_frame')
        if type(start) is not int or type(end) is not int or not 0 <= start < end <= total:
            raise ValueError('文字起止须为有效整数帧，end_frame为不包含的结束帧。')
        if row.get('effect','fade') not in ('fade','rise','pop','none'):
            raise ValueError('基础脚本仅支持fade/rise/pop/none；高级效果须另做。')
        if 'position' in row and (len(row['position']) != 2 or any(not 0 <= v <= 1 for v in row['position'])):
            raise ValueError('position应为画面归一化坐标[x,y]，范围0–1。')
        if row.get('font_size',64) <= 0:
            raise ValueError('font_size必须 > 0。')
        if 'color' in row and (len(row['color']) != 3 or any(not 0 <= v <= 1 for v in row['color'])):
            raise ValueError('color须为0–1的RGB。')
    for kind in ('video','music'):
        row = data.get(kind)
        if not row:
            continue
        if not Path(row['path']).is_absolute() or not Path(row['path']).is_file():
            raise ValueError(kind+'必须是存在的绝对文件路径。')
        start = row.get('timeline_start_frame',0)
        if type(start) is not int or not 0 <= start < total:
            raise ValueError(kind+'时间线起点须为范围内整数帧。')
        if not isinstance(row.get('source_in_seconds',0),(int,float)) or row.get('source_in_seconds',0) < 0:
            raise ValueError(kind+'源入点不可为负。')
    for row in data.get('markers',[]):
        if type(row.get('frame')) is not int or not 0 <= row['frame'] < total:
            raise ValueError('标记帧超出时间线。')
    # Reject NaN / Infinity anywhere, including optional numeric fields.
    json.dumps(data, allow_nan=False)
    return fps


JSX = r'''
(function () {
    var d = __DATA__, out = Folder(__OUT__);
    function log(value) {
        var f = File(out.fsName + "/ae-build-result.json");
        f.encoding = "UTF-8"; f.open("w"); f.write(value); f.close();
    }
    // Never close, overwrite or save a user's open populated/dirty project.
    if (app.project && (app.project.numItems > 0 || app.project.dirty)) {
        log('{"status":"blocked","reason":"请先手动保存并关闭当前工程，脚本未改动它。"}');
        return;
    }
    if (File(out.fsName+"/text-music.aep").exists) {
        log('{"status":"blocked","reason":"目标工程已存在，请使用新版本目录。"}');
        return;
    }
    var began = false;
    try {
        app.beginUndoGroup("Video text music setup"); began = true;
        if (!app.project) app.newProject();
        var rate = d.fps_value, fd = 1/rate;
        var c = app.project.items.addComp(d.name,d.width,d.height,1,d.duration_frames/rate,rate);
        function placeMedia(m, name, music) {
            if (!m) return;
            var item = app.project.importFile(new ImportOptions(File(m.path)));
            var layer = c.layers.add(item); layer.name = name;
            var target = (m.timeline_start_frame || 0) / rate;
            layer.startTime = target - (m.source_in_seconds || 0);
            layer.inPoint = target;
            layer.outPoint = Math.min(c.duration,layer.startTime + item.duration);
            if (music) {
                layer.enabled = false;
                layer.audioEnabled = true;
                if (item.hasAudio && m.gain_db !== undefined)
                    layer.property("ADBE Audio Group").property("ADBE Audio Levels").setValue([m.gain_db,m.gain_db]);
            } else {
                layer.audioEnabled = m.audio_enabled === true;
                var s = Math.min(d.width/item.width,d.height/item.height)*100;
                layer.property("ADBE Transform Group").property("ADBE Scale").setValue([s,s]);
            }
        }
        placeMedia(d.video,"FOOTAGE_source",false);
        placeMedia(d.music,"MUSIC_source",true);
        for (var i=0;i<(d.texts || []).length;i++) {
            var e=d.texts[i], l=c.layers.addText(e.text); l.name="TEXT_"+(e.id || (i+1));
            var source=l.property("ADBE Text Properties").property("ADBE Text Document");
            var doc=source.value; doc.font=e.font || "PingFangSC-Regular";
            doc.fontSize=e.font_size || 64; doc.fillColor=e.color || [0.985,0.977,0.957];
            doc.applyFill=true; doc.applyStroke=false;
            doc.justification=ParagraphJustification.LEFT_JUSTIFY; source.setValue(doc);
            var t=e.start_frame/rate, end=e.end_frame/rate;
            l.inPoint=t; l.outPoint=end;
            var tr=l.property("ADBE Transform Group"), p=e.position || [0.1,0.82];
            var xy=[p[0]*d.width,p[1]*d.height]; tr.property("ADBE Position").setValue(xy);
            var fade=Math.min(0.28,(end-t)/3), effect=e.effect || "fade";
            if (effect !== "none") {
                var opacity=tr.property("ADBE Opacity");
                opacity.setValueAtTime(t,0); opacity.setValueAtTime(t+fade,100);
                opacity.setValueAtTime(end-fade,100); opacity.setValueAtTime(end,0);
            }
            if (effect === "rise") {
                var pos=tr.property("ADBE Position"), move=16*d.height/1080;
                pos.setValueAtTime(t,[xy[0],xy[1]+move]); pos.setValueAtTime(t+fade,xy);
            }
            if (effect === "pop") {
                var scale=tr.property("ADBE Scale");
                scale.setValueAtTime(t,[94,94]); scale.setValueAtTime(t+fade,[100,100]);
            }
            l.comment="mode="+(e.mode || "copy")+"; sync="+(e.sync_status || "pending")+
                      "; event="+(e.sync_event || "unspecified");
        }
        for (var j=0;j<(d.markers || []).length;j++) {
            var m=d.markers[j], mark=new MarkerValue((m.status || "pending")+": "+(m.label || "event"));
            c.markerProperty.setValueAtTime(m.frame/rate,mark);
        }
        c.workAreaStart=0; c.workAreaDuration=c.duration;
        var project=File(out.fsName+"/text-music.aep");
        if (project.exists) throw new Error("目标工程已存在；另选输出目录，不覆盖历史工程。");
        app.project.save(project);
        // Render a still only for inspection; it does not prove timing or final render quality.
        if (d.preview_frame !== undefined)
            c.saveFrameToPng(d.preview_frame/rate,File(out.fsName+"/preview.png"));
        log('{"status":"created","note":"工程已建立，卡点、遮罩、声音与成片仍须动态核验。"}');
    } catch (error) {
        log('{"status":"error","message":"'+String(error).replace(/\\/g,"\\\\").replace(/"/g,'\\"').replace(/[\r\n]/g," ")+'"}');
        throw error;
    } finally {
        if (began) app.endUndoGroup();
    }
})();
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--timeline',required=True)
    parser.add_argument('--out-dir',required=True)
    args=parser.parse_args()
    data=json.loads(Path(args.timeline).read_text(encoding='utf-8'))
    fps=validate(data)
    out=ensure_output(args.out_dir)
    data['fps']=str(fps)
    data['fps_value']=float(fps)
    if 'preview_frame' in data and (type(data['preview_frame']) is not int or not 0 <= data['preview_frame'] < data['duration_frames']):
        raise ValueError('preview_frame超出范围。')
    js=JSX.replace('__DATA__',json.dumps(data,ensure_ascii=True,allow_nan=False)).replace('__OUT__',json.dumps(str(out),ensure_ascii=True))
    (out/'build-text-music.jsx').write_text(js,encoding='utf-8')
    (out/'timeline.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    with (out/'text-timeline.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.writer(stream)
        writer.writerow(['id','text','start_frame','end_frame','start_seconds','end_seconds','mode','effect','sync_status','sync_event'])
        for i,row in enumerate(data.get('texts',[])):
            writer.writerow([row.get('id',i+1),row['text'],row['start_frame'],row['end_frame'],
                             float(Fraction(row['start_frame'])/fps),float(Fraction(row['end_frame'])/fps),
                             row.get('mode','copy'),row.get('effect','fade'),row.get('sync_status','pending'),row.get('sync_event','')])
    print(json.dumps({'jsx':str(out/'build-text-music.jsx'),'status':'script_generated_not_AE_project'},ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except (ValueError,KeyError,TypeError,OSError,ZeroDivisionError) as error:
        print(str(error),file=sys.stderr)
        sys.exit(2)
