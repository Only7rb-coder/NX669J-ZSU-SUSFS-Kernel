#!/usr/bin/env python3
"""Expose v2.2 SUSFS helper APIs using Linux 5.4 mount/statfs internals."""
from __future__ import annotations

import pathlib
import sys

MOUNT_MARKER = "/* NX669J SUSFS v2.2 mount helper API. */"
STATFS_MARKER = "/* NX669J SUSFS v2.2 statfs helper API. */"

MOUNT_BLOCK = r'''

/* NX669J SUSFS v2.2 mount helper API. */
#if defined(CONFIG_KSU_SUSFS_SUS_MOUNT) || defined(CONFIG_KSU_SUSFS_SUS_KSTAT)
int susfs_get_non_sus_mnt_id_from_mnt(struct mount *orig_mnt)
{
	struct mount *mnt = orig_mnt;
	int mnt_id;

	if (!mnt)
		return 0;
	if (mnt->mnt_id < DEFAULT_SUS_MNT_ID)
		return mnt->mnt_id;
	lock_mount_hash();
	for (; mnt && mnt->mnt_parent && mnt != mnt->mnt_parent &&
	       mnt->mnt_id >= DEFAULT_SUS_MNT_ID; mnt = mnt->mnt_parent)
		;
	mnt_id = mnt ? mnt->mnt_id : 0;
	unlock_mount_hash();
	return mnt_id;
}

/* Returned mount and root each carry a reference owned by the caller. */
struct vfsmount *susfs_get_non_sus_vfsmnt_from_vfsmnt(struct vfsmount *vfsmnt)
{
	struct mount *mnt;

	if (!vfsmnt)
		return NULL;
	mnt = real_mount(vfsmnt);
	lock_mount_hash();
	for (; mnt && mnt->mnt_parent && mnt != mnt->mnt_parent &&
	       mnt->mnt_id >= DEFAULT_SUS_MNT_ID; mnt = mnt->mnt_parent)
		;
	if (!mnt || !mnt->mnt.mnt_root || IS_ERR(mnt->mnt.mnt_root)) {
		unlock_mount_hash();
		mntget(vfsmnt);
		dget(vfsmnt->mnt_root);
		return vfsmnt;
	}
	mntget(&mnt->mnt);
	dget(mnt->mnt.mnt_root);
	unlock_mount_hash();
	return &mnt->mnt;
}
#endif
'''

STATFS_BLOCK = r'''

/* NX669J SUSFS v2.2 statfs helper API. */
#ifdef CONFIG_KSU_SUSFS_SUS_KSTAT
int statfs_by_dentry_wrapper(struct dentry *dentry, struct kstatfs *buf)
{
	return statfs_by_dentry(dentry, buf);
}

int calculate_f_flags_wrapper(struct vfsmount *mnt)
{
	return calculate_f_flags(mnt);
}
#endif
'''


def append_once(path: pathlib.Path, marker: str, block: str) -> None:
    text = path.read_text()
    if marker not in text:
        path.write_text(text.rstrip() + block + "\n")


def main() -> int:
    if len(sys.argv) != 3:
        print(f"usage: {sys.argv[0]} NAMESPACE_C STATFS_C", file=sys.stderr)
        return 2
    namespace, statfs = map(pathlib.Path, sys.argv[1:])
    append_once(namespace, MOUNT_MARKER, MOUNT_BLOCK)
    append_once(statfs, STATFS_MARKER, STATFS_BLOCK)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
