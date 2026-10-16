# -*- coding: utf-8 -*-
"""调试 cvarlist 定宽列的切分边界。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import import_cvar_dump as I  # noqa: E402

TXT = (ROOT / "_dumps" / "cs2_cvarlist_full.txt").read_text(encoding="utf-8", errors="replace")

for target in ("cl_ent_text_filter", "menuselect", "snd_sos_test_soundmessage", "cl_radar_rotate"):
    for raw in TXT.splitlines():
        if f"]: {target} " in raw:
            line = I.LOGPREFIX.sub("", raw).rstrip()
            print(f"--- {target}")
            print(f"    len={len(line)}")
            print(f"    colons at {[i for i, c in enumerate(line) if c == ':']}")
            print(f"    [130:160]={line[130:160]!r}")
            print(f"    parsed={I.parse_colon_fields(line)}")
            break
