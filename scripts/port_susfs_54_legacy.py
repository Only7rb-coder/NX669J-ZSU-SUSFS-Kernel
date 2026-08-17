#!/usr/bin/env python3
"""Expose the legacy SUSFS symbols required by the NX669J Linux 5.4 patch.

The v2.2 implementation keeps the same features but renamed several helpers
and changed the path/kstat data model.  This port adds a small compatibility
index populated by the v2.2 command handlers and forwards the old 5.4 VFS
hooks to that index or to the v2.2 open-redirect data.
"""
from __future__ import annotations

import pathlib
import sys

MARKER = "/* NX669J Linux 5.4 SUSFS legacy symbol bridge. */"

STATE = r'''

/* NX669J Linux 5.4 SUSFS legacy symbol bridge. */
/* The 5.4 source patch still calls the v1.x helper names.  Keep a small
 * inode-keyed compatibility index fed by the v2.2 command handlers. */
#ifdef CONFIG_KSU_SUSFS_SUS_PATH
struct nx669j_susfs_path_compat_entry {
	unsigned long target_ino;
	struct hlist_node node;
};
static DEFINE_HASHTABLE(nx669j_susfs_path_compat_hlist, 10);
static DEFINE_MUTEX(nx669j_susfs_path_compat_lock);

static void nx669j_susfs_record_path_ino(unsigned long ino)
{
	struct nx669j_susfs_path_compat_entry *entry;
	bool found = false;

	if (!ino)
		return;
	mutex_lock(&nx669j_susfs_path_compat_lock);
	hash_for_each_possible(nx669j_susfs_path_compat_hlist, entry, node, ino) {
		if (entry->target_ino == ino) {
			found = true;
			break;
		}
	}
	if (!found) {
		entry = kzalloc(sizeof(*entry), GFP_KERNEL);
		if (entry) {
			entry->target_ino = ino;
			hash_add(nx669j_susfs_path_compat_hlist, &entry->node, ino);
		}
	}
	mutex_unlock(&nx669j_susfs_path_compat_lock);
}

int susfs_sus_ino_for_filldir64(unsigned long ino)
{
	struct nx669j_susfs_path_compat_entry *entry;
	bool found = false;

	rcu_read_lock();
	hash_for_each_possible_rcu(nx669j_susfs_path_compat_hlist, entry, node, ino) {
		if (entry->target_ino == ino) {
			found = true;
			break;
		}
	}
	rcu_read_unlock();
	return found ? 1 : 0;
}
#endif

#ifdef CONFIG_KSU_SUSFS_SUS_KSTAT
struct nx669j_susfs_kstat_compat_entry {
	unsigned long target_ino;
	struct st_susfs_sus_kstat info;
	struct hlist_node node;
};
static DEFINE_HASHTABLE(nx669j_susfs_kstat_compat_hlist, 10);
static DEFINE_MUTEX(nx669j_susfs_kstat_compat_lock);

static void nx669j_susfs_record_kstat(const struct st_susfs_sus_kstat *info)
{
	struct nx669j_susfs_kstat_compat_entry *entry;
	bool found = false;

	if (!info || info->err || !info->target_ino)
		return;
	mutex_lock(&nx669j_susfs_kstat_compat_lock);
	hash_for_each_possible(nx669j_susfs_kstat_compat_hlist, entry, node, info->target_ino) {
		if (entry->target_ino == info->target_ino) {
			memcpy(&entry->info, info, sizeof(*info));
			found = true;
			break;
		}
	}
	if (!found) {
		entry = kzalloc(sizeof(*entry), GFP_KERNEL);
		if (entry) {
			entry->target_ino = info->target_ino;
			memcpy(&entry->info, info, sizeof(*info));
			hash_add(nx669j_susfs_kstat_compat_hlist, &entry->node, info->target_ino);
		}
	}
	mutex_unlock(&nx669j_susfs_kstat_compat_lock);
}

static struct nx669j_susfs_kstat_compat_entry *nx669j_susfs_find_kstat(unsigned long ino)
{
	struct nx669j_susfs_kstat_compat_entry *entry;

	hash_for_each_possible(nx669j_susfs_kstat_compat_hlist, entry, node, ino) {
		if (entry->target_ino == ino)
			return entry;
	}
	return NULL;
}

void susfs_sus_ino_for_generic_fillattr(unsigned long ino, struct kstat *stat)
{
	struct nx669j_susfs_kstat_compat_entry *entry;
	struct st_susfs_sus_kstat *info;

	mutex_lock(&nx669j_susfs_kstat_compat_lock);
	entry = nx669j_susfs_find_kstat(ino);
	if (!entry) {
		mutex_unlock(&nx669j_susfs_kstat_compat_lock);
		return;
	}
	info = &entry->info;
	if (info->flags & KSTAT_SPOOF_INO) stat->ino = info->spoofed_ino;
	if (info->flags & KSTAT_SPOOF_DEV) stat->dev = info->spoofed_dev;
	if (info->flags & KSTAT_SPOOF_NLINK) stat->nlink = info->spoofed_nlink;
	if (info->flags & KSTAT_SPOOF_SIZE) stat->size = info->spoofed_size;
	if (info->flags & KSTAT_SPOOF_ATIME_TV_SEC) stat->atime.tv_sec = info->spoofed_atime_tv_sec;
	if (info->flags & KSTAT_SPOOF_ATIME_TV_NSEC) stat->atime.tv_nsec = info->spoofed_atime_tv_nsec;
	if (info->flags & KSTAT_SPOOF_MTIME_TV_SEC) stat->mtime.tv_sec = info->spoofed_mtime_tv_sec;
	if (info->flags & KSTAT_SPOOF_MTIME_TV_NSEC) stat->mtime.tv_nsec = info->spoofed_mtime_tv_nsec;
	if (info->flags & KSTAT_SPOOF_CTIME_TV_SEC) stat->ctime.tv_sec = info->spoofed_ctime_tv_sec;
	if (info->flags & KSTAT_SPOOF_CTIME_TV_NSEC) stat->ctime.tv_nsec = info->spoofed_ctime_tv_nsec;
	if (info->flags & KSTAT_SPOOF_BLKSIZE) stat->blksize = info->spoofed_blksize;
	if (info->flags & KSTAT_SPOOF_BLOCKS) stat->blocks = info->spoofed_blocks;
	mutex_unlock(&nx669j_susfs_kstat_compat_lock);
}

void susfs_sus_ino_for_show_map_vma(unsigned long ino, dev_t *out_dev, unsigned long *out_ino)
{
	struct nx669j_susfs_kstat_compat_entry *entry;

	mutex_lock(&nx669j_susfs_kstat_compat_lock);
	entry = nx669j_susfs_find_kstat(ino);
	if (entry) {
		if (entry->info.flags & KSTAT_SPOOF_DEV)
			*out_dev = entry->info.spoofed_dev;
		if (entry->info.flags & KSTAT_SPOOF_INO)
			*out_ino = entry->info.spoofed_ino;
	}
	mutex_unlock(&nx669j_susfs_kstat_compat_lock);
}
#endif

#ifdef CONFIG_KSU_SUSFS_OPEN_REDIRECT
struct filename *susfs_get_redirected_path(unsigned long ino)
{
	struct st_susfs_open_redirect_hlist *entry = NULL;
	struct filename *new_filename = NULL;
	int srcu_idx = srcu_read_lock(&susfs_srcu_open_redirect);

	hash_for_each_possible_rcu(OPEN_REDIRECT_HLIST, entry, node, ino) {
		if (!entry->reversed_lookup_only && entry->target_ino == ino) {
			switch (entry->info.uid_scheme) {
			case UID_NON_APP_PROC:
				if (current_uid().val % 100000 < 10000) break;
				goto out_srcu_read_unlock;
			case UID_ROOT_PROC_EXCEPT_SU_PROC:
				if (current_uid().val == 0 && !susfs_is_current_ksu_domain()) break;
				goto out_srcu_read_unlock;
			case UID_NON_SU_PROC:
				if (!susfs_is_current_ksu_domain()) break;
				goto out_srcu_read_unlock;
			case UID_UMOUNTED_APP_PROC:
				if (susfs_is_current_proc_umounted_app()) break;
				goto out_srcu_read_unlock;
			case UID_UMOUNTED_PROC:
				if (susfs_is_current_proc_umounted()) break;
				goto out_srcu_read_unlock;
			default:
				goto out_srcu_read_unlock;
			}
			new_filename = getname_kernel(entry->info.redirected_pathname);
			break;
		}
	}
out_srcu_read_unlock:
	srcu_read_unlock(&susfs_srcu_open_redirect, srcu_idx);
	return new_filename;
}
#endif

#ifdef CONFIG_KSU_SUSFS_SUS_MOUNT
/* v2.2 performs mount hiding through static keys and per-process state; the
 * legacy 5.4 caller invokes this after umount only to reorder old mount IDs. */
void susfs_reorder_mnt_id(void)
{
}
#endif
'''


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise ValueError(f"expected one {label}, found {count}")
    return text.replace(old, new, 1)


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} PATH", file=sys.stderr)
        return 2
    path = pathlib.Path(sys.argv[1])
    text = path.read_text()
    if MARKER in text:
        return 0

    text = replace_once(
        text,
        'static void susfs_run_sus_path_loop(void) {',
        'void susfs_run_sus_path_loop(uid_t uid) {\n\t(void)uid;',
        "path-loop declaration",
    )
    text = replace_once(text, 'susfs_run_sus_path_loop();', 'susfs_run_sus_path_loop(0);', "path-loop call")

    # Feed the legacy inode index at every v2.2 path-marking point.
    text = replace_once(
        text,
        '\t\tset_bit(AS_FLAGS_SUS_PATH, &inode->i_mapping->flags);\n\t\tSUSFS_LOGI("flagged AS_FLAGS_SUS_PATH',
        '\t\tset_bit(AS_FLAGS_SUS_PATH, &inode->i_mapping->flags);\n\t\tnx669j_susfs_record_path_ino(fi->inode.i_ino);\n\t\tnx669j_susfs_record_path_ino(inode->i_ino);\n\t\tSUSFS_LOGI("flagged AS_FLAGS_SUS_PATH',
        "FUSE path record",
    )
    text = replace_once(
        text,
        '\tset_bit(AS_FLAGS_SUS_PATH, &inode->i_mapping->flags);\n\tSUSFS_LOGI("flagged AS_FLAGS_SUS_PATH',
        '\tset_bit(AS_FLAGS_SUS_PATH, &inode->i_mapping->flags);\n\tnx669j_susfs_record_path_ino(inode->i_ino);\n\tSUSFS_LOGI("flagged AS_FLAGS_SUS_PATH',
        "normal path record",
    )
    text = replace_once(
        text,
        '\t\t\t\tset_bit(AS_FLAGS_SUS_PATH, &fi->inode.i_mapping->flags);\n\t\t\t\tset_bit(AS_FLAGS_SUS_PATH, &inode->i_mapping->flags);\n\t\t\t\tSUSFS_LOGI("re-flag AS_FLAGS_SUS_PATH',
        '\t\t\t\tset_bit(AS_FLAGS_SUS_PATH, &fi->inode.i_mapping->flags);\n\t\t\t\tset_bit(AS_FLAGS_SUS_PATH, &inode->i_mapping->flags);\n\t\t\t\tnx669j_susfs_record_path_ino(fi->inode.i_ino);\n\t\t\t\tnx669j_susfs_record_path_ino(inode->i_ino);\n\t\t\t\tSUSFS_LOGI("re-flag AS_FLAGS_SUS_PATH',
        "FUSE loop record",
    )
    text = replace_once(
        text,
        '\t\t\t\tset_bit(AS_FLAGS_SUS_PATH, &inode->i_mapping->flags);\n\t\t\t\tSUSFS_LOGI("re-flag AS_FLAGS_SUS_PATH',
        '\t\t\t\tset_bit(AS_FLAGS_SUS_PATH, &inode->i_mapping->flags);\n\t\t\t\tnx669j_susfs_record_path_ino(inode->i_ino);\n\t\t\t\tSUSFS_LOGI("re-flag AS_FLAGS_SUS_PATH',
        "normal loop record",
    )

    # Record v2.2 kstat command state after the command has validated it.
    text = replace_once(
        text,
        '\tif (!info.is_statically) {\n\t\tSUSFS_LOGI("CMD_SUSFS_ADD_SUS_KSTAT -> ret: %d\\n", info.err);',
        '\tif (!info.err) nx669j_susfs_record_kstat(&info);\n\tif (!info.is_statically) {\n\t\tSUSFS_LOGI("CMD_SUSFS_ADD_SUS_KSTAT -> ret: %d\\n", info.err);',
        "kstat add anchor",
    )
    text = replace_once(
        text,
        '\tSUSFS_LOGI("CMD_SUSFS_UPDATE_SUS_KSTAT -> ret: %d\\n", info.err);',
        '\tif (!info.err) nx669j_susfs_record_kstat(&info);\n\tSUSFS_LOGI("CMD_SUSFS_UPDATE_SUS_KSTAT -> ret: %d\\n", info.err);',
        "kstat update anchor",
    )

    anchor = '#include "mount.h"\n'
    prototypes = '''
#ifdef CONFIG_KSU_SUSFS_SUS_PATH
static void nx669j_susfs_record_path_ino(unsigned long ino);
#endif
#ifdef CONFIG_KSU_SUSFS_SUS_KSTAT
static void nx669j_susfs_record_kstat(const struct st_susfs_sus_kstat *info);
#endif
'''
    text = replace_once(text, anchor, anchor + prototypes, "legacy bridge declaration anchor")
    text += STATE
    path.write_text(text)
    print(f"added Linux 5.4 SUSFS legacy symbol bridge to {path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
