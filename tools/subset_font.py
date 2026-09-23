"""Subset Pretendard Variable in place: Latin + UI symbols + KS X 1001 Hangul (2,350 syllables). Keeps the weight axis."""

import os
import sys
from pathlib import Path

from fontTools import subset

RANGES = [(0x0000, 0x00FF), (0x2000, 0x206F), (0x20A0, 0x20CF), (0x2190, 0x21FF), (0x2200, 0x22FF),
          (0x2460, 0x24FF), (0x2500, 0x25FF), (0x2700, 0x27BF), (0x27F0, 0x27FF), (0x3000, 0x303F),
          (0x3130, 0x318F), (0xFF00, 0xFFEF)]


def codepoints():
    cps = {c for a, b in RANGES for c in range(a, b + 1)}
    for hi in range(0xB0, 0xC9):  # KS X 1001 Hangul block: 2,350 syllables
        for lo in range(0xA1, 0xFF):
            try:
                cps.add(ord(bytes([hi, lo]).decode("euc-kr")))
            except UnicodeDecodeError:
                pass
    return sorted(cps)


def main(path):
    path = Path(path)
    opts = subset.Options(flavor="woff2", layout_features=["*"], notdef_outline=True)
    font = subset.load_font(str(path), opts)
    s = subset.Subsetter(opts)
    s.populate(unicodes=codepoints())
    s.subset(font)
    tmp = path.with_suffix(".tmp.woff2")
    subset.save_font(font, str(tmp), opts)
    before, after = path.stat().st_size, tmp.stat().st_size
    os.replace(tmp, path)
    print(f"{path}: {before:,} -> {after:,} bytes")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "dashboard/assets/fonts/PretendardVariable.woff2")
