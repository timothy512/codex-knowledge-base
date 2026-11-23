#!/usr/bin/env python3
"""Create white-background EAN-13 artwork using only the Python standard library."""

import argparse
import itertools
import re
import struct
import sys
import zlib
from decimal import Decimal
from pathlib import Path


LEFT_ODD = (
    "0001101", "0011001", "0010011", "0111101", "0100011",
    "0110001", "0101111", "0111011", "0110111", "0001011",
)
RIGHT = tuple(pattern.translate(str.maketrans("01", "10")) for pattern in LEFT_ODD)
LEFT_EVEN = tuple(pattern[::-1] for pattern in RIGHT)
LEFT_PARITY = (
    "LLLLLL", "LLGLGG", "LLGGLG", "LLGGGL", "LGLLGG",
    "LGGLLG", "LGGGLL", "LGLGLG", "LGLGGL", "LGGLGL",
)

# Artwork coordinates are hundredths of a millimetre at nominal size.
MODULE = 33
LEFT_QUIET_MODULES = 11
RIGHT_QUIET_MODULES = 7
SYMBOL_MODULES = 95
WIDTH = (LEFT_QUIET_MODULES + SYMBOL_MODULES + RIGHT_QUIET_MODULES) * MODULE
HEIGHT = 2593
BAR_HEIGHT = 2285
GUARD_HEIGHT = BAR_HEIGHT + 5 * MODULE
GUARD_BARS = frozenset((0, 2, 46, 48, 92, 94))
PIXELS_PER_MODULE = 8

# A fixed, font-independent 5 × 7 alphabet keeps SVGs portable in print apps.
DIGITS = (
    (14, 17, 17, 17, 17, 17, 14),
    (4, 12, 4, 4, 4, 4, 14),
    (14, 17, 1, 2, 4, 8, 31),
    (30, 1, 1, 14, 1, 1, 30),
    (2, 6, 10, 18, 31, 2, 2),
    (31, 16, 16, 30, 1, 1, 30),
    (14, 16, 16, 30, 17, 17, 14),
    (31, 1, 2, 4, 8, 8, 8),
    (14, 17, 17, 14, 17, 17, 14),
    (14, 17, 17, 15, 1, 1, 14),
)


def normalize_code(raw):
    code = raw.strip()
    if not re.fullmatch(r"[0-9]{12,13}", code):
        raise ValueError(f"{raw!r}: expected 12 or 13 digits (0–9).")

    weighted_sum = sum(int(digit) for digit in code[:12:2])
    weighted_sum += 3 * sum(int(digit) for digit in code[1:12:2])
    check_digit = str(-weighted_sum % 10)
    if len(code) == 12:
        return code + check_digit
    if code[-1] != check_digit:
        raise ValueError(
            f"{code}: invalid check digit {code[-1]}. "
            f"Expected {check_digit} for the supplied first 12 digits."
        )
    return code


def encode_modules(code):
    parity = LEFT_PARITY[int(code[0])]
    left = "".join(
        (LEFT_ODD if kind == "L" else LEFT_EVEN)[int(digit)]
        for kind, digit in zip(parity, code[1:7])
    )
    right = "".join(RIGHT[int(digit)] for digit in code[7:])
    return f"101{left}01010{right}101"


def black_runs(bits):
    offset = 0
    for bit, run in itertools.groupby(bits):
        length = sum(1 for _ in run)
        if bit == "1":
            yield offset, length
        offset += length


def artwork(code):
    rectangles = []
    for start, length in black_runs(encode_modules(code)):
        x = (LEFT_QUIET_MODULES + start) * MODULE
        height = GUARD_HEIGHT if start in GUARD_BARS else BAR_HEIGHT
        rectangles.append((x, 0, length * MODULE, height))

    left_start = LEFT_QUIET_MODULES + 3
    right_start = left_start + 42 + 5
    first_center = LEFT_QUIET_MODULES * MODULE // 2
    centers = [first_center]
    for group_start in (left_start, right_start):
        for index in range(6):
            centers.append((group_start + 7 * index) * MODULE + 7 * MODULE // 2)

    cell_width, cell_height = 33, 37
    digit_top = 2330
    for digit, center in zip(code, centers):
        left = center - 5 * cell_width // 2
        for row, mask in enumerate(DIGITS[int(digit)]):
            for start, length in black_runs(f"{mask:05b}"):
                rectangles.append((
                    left + start * cell_width,
                    digit_top + row * cell_height,
                    length * cell_width,
                    cell_height,
                ))
    return rectangles


def svg_image(code, rectangles, scale):
    width_mm = WIDTH * scale / 10000
    height_mm = HEIGHT * scale / 10000
    path = "".join(f"M{x} {y}h{w}v{h}h-{w}z" for x, y, w, h in rectangles)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width_mm:f}mm" '
        f'height="{height_mm:f}mm" viewBox="0 0 {WIDTH} {HEIGHT}" '
        f'role="img" aria-labelledby="barcode-title">\n'
        f'  <title id="barcode-title">EAN-13 {code}</title>\n'
        f'  <rect width="{WIDTH}" height="{HEIGHT}" fill="#fff"/>\n'
        f'  <path fill="#000" d="{path}"/>\n'
        '</svg>\n'
    )


def png_chunk(kind, data):
    payload = kind + data
    return struct.pack(">I", len(data)) + payload + struct.pack(">I", zlib.crc32(payload))


def png_image(code, rectangles, scale):
    def pixel(units):
        return (units * PIXELS_PER_MODULE + MODULE // 2) // MODULE

    width, height = pixel(WIDTH), pixel(HEIGHT)
    stride = width + 1  # One leading filter byte per row.
    rows = bytearray((b"\x00" + b"\xff" * width) * height)
    for x, y, w, h in rectangles:
        left, right = pixel(x), pixel(x + w)
        black = bytes(right - left)
        for row in range(pixel(y), pixel(y + h)):
            start = row * stride + 1 + left
            rows[start:start + len(black)] = black

    pixels_per_metre = round(PIXELS_PER_MODULE * 10000000 / (MODULE * scale))
    return b"".join((
        b"\x89PNG\r\n\x1a\n",
        png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)),
        png_chunk(b"pHYs", struct.pack(">IIB", pixels_per_metre, pixels_per_metre, 1)),
        png_chunk(b"tEXt", b"Title\x00EAN-13 " + code.encode("ascii")),
        png_chunk(b"IDAT", zlib.compress(rows)),
        png_chunk(b"IEND", b""),
    ))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("codes", nargs="+", help="12-digit EAN-13 bases or valid 13-digit codes")
    parser.add_argument("--output-dir", type=Path, default=Path("."))
    parser.add_argument("--format", choices=("svg", "png", "both"), default="both")
    parser.add_argument("--scale", type=Decimal, default=Decimal(100), help="percent, 80–200")
    args = parser.parse_args()
    if not args.scale.is_finite() or not 80 <= args.scale <= 200:
        parser.error("--scale must be between 80 and 200 percent.")

    normalized = {}
    for raw in args.codes:
        try:
            normalized[raw] = normalize_code(raw)
        except ValueError as error:
            parser.error(str(error))

    try:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        for code in dict.fromkeys(normalized.values()):
            rectangles = artwork(code)
            stem = args.output_dir / f"EAN13-{code}"
            if args.format in ("svg", "both"):
                path = stem.with_suffix(".svg")
                path.write_text(svg_image(code, rectangles, args.scale), encoding="utf-8")
                print(f"{code}\t{path}")
            if args.format in ("png", "both"):
                path = stem.with_suffix(".png")
                path.write_bytes(png_image(code, rectangles, args.scale))
                print(f"{code}\t{path}")
    except OSError as error:
        parser.exit(1, f"Could not write barcode artwork: {error}\n")


if __name__ == "__main__":
    sys.exit(main())
