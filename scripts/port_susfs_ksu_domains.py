#!/usr/bin/env python3
"""Bridge SUSFS domain predicates to KernelSU-Next's SELinux domain checks."""
from __future__ import annotations

import pathlib
import sys

MARKER = "/* NX669J SUSFS domain predicate bridge. */"
REQUIRED = (
    "bool is_ksu_domain(void)",
    "bool is_zygote(const struct cred *cred)",
)
BRIDGE = r'''

/* NX669J SUSFS domain predicate bridge. */
/* SUSFS expects these names; KernelSU-Next owns the canonical SELinux SID checks. */
bool susfs_is_current_ksu_domain(void)
{
	return is_ksu_domain();
}

bool susfs_is_current_zygote_domain(void)
{
	return is_zygote(current_cred());
}
'''


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} PATH", file=sys.stderr)
        return 2

    path = pathlib.Path(sys.argv[1])
    text = path.read_text()
    missing = [signature for signature in REQUIRED if signature not in text]
    if missing:
        print(
            "KernelSU-Next SELinux domain API changed; missing: " + ", ".join(missing),
            file=sys.stderr,
        )
        return 1

    if MARKER in text:
        return 0

    text = text.rstrip() + BRIDGE
    path.write_text(text)
    print(f"added SUSFS domain predicate bridge to {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
