#!/usr/bin/env python3
"""Port the SUSFS inotify fd-info mask expression to the NX669J 5.4 tree."""
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: port_inotify_susfs.py /path/to/fs/notify/fdinfo.c")

path = Path(sys.argv[1])
text = path.read_text()
needle = "inotify_mark_user_mask(mark)"
replacement = "(mark->mask & IN_ALL_EVENTS)"
count = text.count(needle)
if count == 0:
    raise SystemExit("expected inotify_mark_user_mask(mark) in patched fs/notify/fdinfo.c")
path.write_text(text.replace(needle, replacement))
print(f"Ported {count} SUSFS inotify mask expression(s) in {path}")
