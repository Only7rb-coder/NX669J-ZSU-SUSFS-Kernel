#!/usr/bin/env python3
"""Add Linux 5.4 compatibility definitions to the v2.2 SUSFS header."""
from __future__ import annotations

import pathlib
import sys

MARKER = "/* NX669J Linux 5.4 compatibility definitions. */"
CRED_INCLUDE = "#include <linux/cred.h>\n"
BLOCK = """

/* NX669J Linux 5.4 compatibility definitions. */
/* The kernel-5.4 SUSFS patch still uses the v1.x mount/task/inode fields. */
#ifndef DEFAULT_SUS_MNT_ID
#define DEFAULT_SUS_MNT_ID 100000
#endif
#ifndef DEFAULT_SUS_MNT_ID_FOR_KSU_PROC_UNSHARE
#define DEFAULT_SUS_MNT_ID_FOR_KSU_PROC_UNSHARE 1000000
#endif
#ifndef DEFAULT_SUS_MNT_GROUP_ID
#define DEFAULT_SUS_MNT_GROUP_ID 1000
#endif
#ifndef INODE_STATE_SUS_PATH
#define INODE_STATE_SUS_PATH BIT(24)
#endif
#ifndef INODE_STATE_SUS_MOUNT
#define INODE_STATE_SUS_MOUNT BIT(25)
#endif
#ifndef INODE_STATE_SUS_KSTAT
#define INODE_STATE_SUS_KSTAT BIT(26)
#endif
#ifndef INODE_STATE_OPEN_REDIRECT
#define INODE_STATE_OPEN_REDIRECT BIT(27)
#endif
#ifndef TASK_STRUCT_NON_ROOT_USER_APP_PROC
#define TASK_STRUCT_NON_ROOT_USER_APP_PROC BIT(24)
#endif
/* v2.2 removed these deprecated v1.x command handlers. KernelSU-Next's
 * legacy-susfs supercalls file still references them unconditionally. */
#ifndef KSU_SUSFS_54_DEPRECATED_API
#define KSU_SUSFS_54_DEPRECATED_API
static inline void susfs_set_i_state_on_external_dir(void *user_info)
{
    (void)user_info;
}
#endif
"""


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} PATH", file=sys.stderr)
        return 2

    path = pathlib.Path(sys.argv[1])
    text = path.read_text()
    if MARKER in text:
        return 0

    end = "#endif // #ifndef KSU_SUSFS_DEF_H"
    anchor = "#include <linux/bits.h>\n"
    if end not in text or anchor not in text:
        print(f"unexpected SUSFS definition header layout in {path}", file=sys.stderr)
        return 1

    text = text.replace(CRED_INCLUDE, "")
    text = text.replace(anchor, anchor + CRED_INCLUDE, 1)
    text = text.replace(end, BLOCK + "\n" + end, 1)
    path.write_text(text)
    print(f"added Linux 5.4 SUSFS compatibility definitions to {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
