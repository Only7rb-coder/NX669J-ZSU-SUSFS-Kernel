#!/usr/bin/env python3
"""Adapt the v2.3 SUSFS fsnotify callback to Linux 5.4."""
from __future__ import annotations

import pathlib
import sys

OLD_SIGNATURE = """static int susfs_handle_sdcard_inode_event(struct fsnotify_mark *mark, u32 mask,
\t\t\t\t\t\t\t\t\t\t\tstruct inode *inode, struct inode *dir,
\t\t\t\t\t\t\t\t\t\t\tconst struct qstr *file_name, u32 cookie)
"""
NEW_SIGNATURE = """static int susfs_handle_sdcard_inode_event(struct fsnotify_group *group,
\t\t\t\t\t\t\t\t\t\t\tstruct inode *inode, u32 mask,
\t\t\t\t\t\t\t\t\t\t\tconst void *data, int data_type,
\t\t\t\t\t\t\t\t\t\t\tconst struct qstr *file_name, u32 cookie,
\t\t\t\t\t\t\t\t\t\t\tstruct fsnotify_iter_info *iter_info)
"""
OLD_FIELD = "\t.handle_inode_event = susfs_handle_sdcard_inode_event,"
NEW_FIELD = "\t.handle_event = susfs_handle_sdcard_inode_event,"


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} PATH", file=sys.stderr)
        return 2
    path = pathlib.Path(sys.argv[1])
    text = path.read_text()
    if NEW_SIGNATURE in text and NEW_FIELD in text:
        return 0
    if OLD_SIGNATURE not in text or OLD_FIELD not in text:
        print(f"unexpected SUSFS fsnotify layout in {path}", file=sys.stderr)
        return 1
    text = text.replace(OLD_SIGNATURE, NEW_SIGNATURE, 1)
    text = text.replace(OLD_FIELD, NEW_FIELD, 1)
    path.write_text(text)
    print(f"ported SUSFS fsnotify callback to Linux 5.4 ABI in {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
