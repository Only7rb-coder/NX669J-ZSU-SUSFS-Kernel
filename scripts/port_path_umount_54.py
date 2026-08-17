#!/usr/bin/env python3
"""Ensure the KernelSU 5.4 path_umount backport is present before kbuild."""
from __future__ import annotations

import pathlib
import sys

PATH_MARKER = "/* NX669J Linux 5.4 path_umount compatibility backport. */"
CAN_UMOUNT = r'''/* NX669J Linux 5.4 path_umount compatibility backport. */
static int can_umount(const struct path *path, int flags)
{
	struct mount *mnt = real_mount(path->mnt);
	if (flags & ~(MNT_FORCE | MNT_DETACH | MNT_EXPIRE | UMOUNT_NOFOLLOW))
		return -EINVAL;
	if (!may_mount())
		return -EPERM;
	if (path->dentry != path->mnt->mnt_root)
		return -EINVAL;
	if (!check_mnt(mnt))
		return -EINVAL;
	if (mnt->mnt.mnt_flags & MNT_LOCKED)
		return -EINVAL;
	if (flags & MNT_FORCE && !capable(CAP_SYS_ADMIN))
		return -EPERM;
	return 0;
}

int path_umount(struct path *path, int flags)
{
	struct mount *mnt = real_mount(path->mnt);
	int ret;

	ret = can_umount(path, flags);
	if (!ret)
		ret = do_umount(mnt, flags);
	dput(path->dentry);
	mntput_no_expire(mnt);
	return ret;
}

'''


def main() -> int:
    if len(sys.argv) != 3:
        print(f"usage: {sys.argv[0]} NAMESPACE_C INTERNAL_H", file=sys.stderr)
        return 2
    namespace = pathlib.Path(sys.argv[1])
    internal = pathlib.Path(sys.argv[2])
    ns_text = namespace.read_text()
    if "int path_umount(struct path *path, int flags)" not in ns_text:
        anchor = "static bool is_mnt_ns_file(struct dentry *dentry)"
        if anchor not in ns_text:
            print(f"cannot locate namespace insertion anchor in {namespace}", file=sys.stderr)
            return 1
        ns_text = ns_text.replace(anchor, CAN_UMOUNT + anchor, 1)
        namespace.write_text(ns_text)

    internal_text = internal.read_text()
    if "int path_umount(struct path *path, int flags);" not in internal_text:
        anchor = "extern void __init mnt_init"
        if anchor not in internal_text:
            print(f"cannot locate internal.h insertion anchor in {internal}", file=sys.stderr)
            return 1
        line_end = internal_text.find("\n", internal_text.index(anchor))
        declaration = "\nint path_umount(struct path *path, int flags);"
        internal_text = internal_text[:line_end] + declaration + internal_text[line_end:]
        internal.write_text(internal_text)

    print(f"verified Linux 5.4 path_umount backport in {namespace}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
