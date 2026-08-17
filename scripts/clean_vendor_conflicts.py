#!/usr/bin/env python3
"""Resolve the known conflict blocks in NX669J rtc-pm8xxx.c.

The source branch contains conflict markers around optional ZTEMT_POWER_DEBUG
resume/suspend instrumentation and one probe IRQ error-message variant. The
NX669J device contract keeps the HEAD side of each conflict and removes the
vendor branch, but refuses any different conflict layout.
"""
from __future__ import annotations

import pathlib
import sys


START = "<<<<<<< HEAD\n"
SEPARATOR = "=======\n"
END = ">>>>>>> bb98672f2897 (first commit)\n"
MARKERS = ("<<<<<<<", "=======", ">>>>>>>")


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} PATH", file=sys.stderr)
        return 2
    path = pathlib.Path(sys.argv[1])
    lines = path.read_text().splitlines(keepends=True)
    output: list[str] = []
    removed = 0
    i = 0
    while i < len(lines):
        if lines[i] == START:
            separator = i + 1
            while separator < len(lines) and lines[separator] != SEPARATOR:
                separator += 1
            if separator >= len(lines):
                print(f"unexpected conflict without separator in {path}", file=sys.stderr)
                return 1
            end = separator + 1
            while end < len(lines) and lines[end] != END:
                end += 1
            if end >= len(lines):
                print(f"unexpected conflict without expected end marker in {path}", file=sys.stderr)
                return 1
            # Keep the HEAD side and discard the vendor side plus all markers.
            output.extend(lines[i + 1 : separator])
            i = end + 1
            removed += 1
            continue
        output.append(lines[i])
        i += 1
    cleaned = "".join(output)
    if any(line.startswith(MARKERS) for line in cleaned.splitlines()):
        print(f"unexpected conflict markers remain in {path}", file=sys.stderr)
        return 1
    if removed:
        path.write_text(cleaned)
        print(f"resolved {removed} known conflict block(s) in {path} using HEAD")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
