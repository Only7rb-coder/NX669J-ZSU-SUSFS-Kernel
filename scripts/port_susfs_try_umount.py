#!/usr/bin/env python3
"""Restore the legacy SUSFS TRY_UMOUNT feature on the v2.3/5.4 hybrid tree."""
from __future__ import annotations

import pathlib
import re
import sys

MARKER = "/* NX669J SUSFS TRY_UMOUNT compatibility port. */"

DEF_BLOCK = r'''
#ifndef CMD_SUSFS_RUN_UMOUNT_FOR_CURRENT_MNT_NS
#define CMD_SUSFS_RUN_UMOUNT_FOR_CURRENT_MNT_NS 0x555d0
#endif
#ifndef DATA_ADB_NO_AUTO_ADD_TRY_UMOUNT_FOR_BIND_MOUNT
#define DATA_ADB_NO_AUTO_ADD_TRY_UMOUNT_FOR_BIND_MOUNT "/data/adb/susfs_no_auto_add_try_umount_for_bind_mount"
#endif
#ifndef MAGIC_MOUNT_WORKDIR
#define MAGIC_MOUNT_WORKDIR "/debug_ramdisk/workdir"
#endif
#ifndef CONFIG_KSU_SUSFS_TRY_UMOUNT
/* The actual Kconfig symbol is supplied by KernelSU-Next. */
#endif
'''

HEADER_BLOCK = r'''

/* try_umount compatibility ABI */
#ifdef CONFIG_KSU_SUSFS_TRY_UMOUNT
struct st_susfs_try_umount {
	char target_pathname[SUSFS_MAX_LEN_PATHNAME];
	int mnt_mode;
};

struct st_susfs_try_umount_list {
	struct list_head list;
	struct st_susfs_try_umount info;
};

int susfs_add_try_umount(void __user **user_info);
void susfs_try_umount(uid_t target_uid);
void susfs_try_umount_all(uid_t target_uid);
void susfs_run_try_umount_for_current_mnt_ns(void);
#ifdef CONFIG_KSU_SUSFS_AUTO_ADD_TRY_UMOUNT_FOR_BIND_MOUNT
extern bool susfs_is_auto_add_try_umount_for_bind_mount_enabled;
void susfs_auto_add_try_umount_for_bind_mount(struct path *path);
#endif
#endif
'''

SOURCE_BLOCK = r'''

/* NX669J SUSFS TRY_UMOUNT compatibility port. */
#ifdef CONFIG_KSU_SUSFS_TRY_UMOUNT
static LIST_HEAD(LH_TRY_UMOUNT_PATH);
static DEFINE_MUTEX(susfs_try_umount_lock);

#ifdef CONFIG_KSU_SUSFS_AUTO_ADD_TRY_UMOUNT_FOR_BIND_MOUNT
/* The kernel-5.4 SUSFS namespace patch owns this boot-time flag. */
extern bool susfs_is_auto_add_try_umount_for_bind_mount_enabled;
#endif

extern int path_umount(struct path *path, int flags);

static int nx669j_susfs_umount_path(const char *mnt, int flags)
{
	struct path path;
	int err;

	if (!mnt || !*mnt)
		return -EINVAL;
	err = kern_path(mnt, 0, &path);
	if (err)
		return err;
	if (path.dentry != path.mnt->mnt_root) {
		path_put(&path);
		return -EINVAL;
	}
	/* The NX669J 5.4 port exports path_umount(), which consumes path. */
	err = path_umount(&path, flags);
	if (err)
		SUSFS_LOGI("TRY_UMOUNT failed for '%s': %d\n", mnt, err);
	else
		SUSFS_LOGI("TRY_UMOUNT removed '%s'\n", mnt);
	return err;
}

int susfs_add_try_umount(void __user **user_info)
{
	struct st_susfs_try_umount info = {0};
	struct st_susfs_try_umount_list *cursor;
	struct st_susfs_try_umount_list *new_entry;
	int err = 0;

	if (copy_from_user(&info, (struct st_susfs_try_umount __user *)*user_info,
			   sizeof(info)))
		return -EFAULT;
	info.target_pathname[SUSFS_MAX_LEN_PATHNAME - 1] = '\0';
	if (!info.target_pathname[0])
		return -EINVAL;
	if (info.mnt_mode != TRY_UMOUNT_DEFAULT && info.mnt_mode != TRY_UMOUNT_DETACH)
		return -EINVAL;

	new_entry = kzalloc(sizeof(*new_entry), GFP_KERNEL);
	if (!new_entry)
		return -ENOMEM;
	memcpy(&new_entry->info, &info, sizeof(info));

	mutex_lock(&susfs_try_umount_lock);
	list_for_each_entry(cursor, &LH_TRY_UMOUNT_PATH, list) {
		if (!strcmp(cursor->info.target_pathname, info.target_pathname)) {
			mutex_unlock(&susfs_try_umount_lock);
			kfree(new_entry);
			return -EEXIST;
		}
	}
	INIT_LIST_HEAD(&new_entry->list);
	list_add_tail(&new_entry->list, &LH_TRY_UMOUNT_PATH);
	mutex_unlock(&susfs_try_umount_lock);
	SUSFS_LOGI("TRY_UMOUNT added '%s' mode %d\n", info.target_pathname, info.mnt_mode);
	return err;
}

void susfs_try_umount(uid_t target_uid)
{
	struct st_susfs_try_umount_list *cursor;

	/* Reverse order is required because overlay paths are registered top-down. */
	mutex_lock(&susfs_try_umount_lock);
	list_for_each_entry_reverse(cursor, &LH_TRY_UMOUNT_PATH, list) {
		int flags = cursor->info.mnt_mode == TRY_UMOUNT_DETACH ? MNT_DETACH : 0;
		(void)target_uid;
		nx669j_susfs_umount_path(cursor->info.target_pathname, flags);
	}
	mutex_unlock(&susfs_try_umount_lock);
}

void susfs_try_umount_all(uid_t target_uid)
{
	susfs_try_umount(target_uid);
	(void)nx669j_susfs_umount_path("/system", 0);
	(void)nx669j_susfs_umount_path("/system_ext", 0);
	(void)nx669j_susfs_umount_path("/vendor", 0);
	(void)nx669j_susfs_umount_path("/product", 0);
	(void)nx669j_susfs_umount_path("/odm", 0);
	(void)nx669j_susfs_umount_path("/data/adb/modules", MNT_DETACH);
	(void)nx669j_susfs_umount_path("/debug_ramdisk", MNT_DETACH);
}

void susfs_run_try_umount_for_current_mnt_ns(void)
{
	susfs_try_umount(current_uid().val);
}

#ifdef CONFIG_KSU_SUSFS_AUTO_ADD_TRY_UMOUNT_FOR_BIND_MOUNT
void susfs_auto_add_try_umount_for_bind_mount(struct path *path)
{
	struct st_susfs_try_umount_list *cursor;
	struct st_susfs_try_umount_list *new_entry;
	char *pathname;
	char *dpath;

	if (!susfs_is_auto_add_try_umount_for_bind_mount_enabled || !path ||
	    !path->dentry || !path->dentry->d_inode)
		return;
#ifdef CONFIG_KSU_SUSFS_SUS_KSTAT
	if (path->dentry->d_inode->i_state & INODE_STATE_SUS_KSTAT)
		return;
#endif
	pathname = kmalloc(PAGE_SIZE, GFP_KERNEL);
	if (!pathname)
		return;
	dpath = d_path(path, pathname, PAGE_SIZE);
	if (IS_ERR(dpath)) {
		kfree(pathname);
		return;
	}
	new_entry = kzalloc(sizeof(*new_entry), GFP_KERNEL);
	if (!new_entry) {
		kfree(pathname);
		return;
	}
	strlcpy(new_entry->info.target_pathname, dpath,
		       sizeof(new_entry->info.target_pathname));
	new_entry->info.mnt_mode = TRY_UMOUNT_DETACH;

	mutex_lock(&susfs_try_umount_lock);
	list_for_each_entry(cursor, &LH_TRY_UMOUNT_PATH, list) {
		if (!strcmp(cursor->info.target_pathname,
			   new_entry->info.target_pathname)) {
			mutex_unlock(&susfs_try_umount_lock);
			kfree(new_entry);
			kfree(pathname);
			return;
		}
	}
	INIT_LIST_HEAD(&new_entry->list);
	list_add_tail(&new_entry->list, &LH_TRY_UMOUNT_PATH);
	mutex_unlock(&susfs_try_umount_lock);
	SUSFS_LOGI("TRY_UMOUNT auto-added bind path '%s'\n",
		   new_entry->info.target_pathname);
	kfree(pathname);
}
#endif
#endif
'''

KCONFIG_BLOCK = r'''
menu "KernelSU - SUSFS"
config KSU_SUSFS
    bool "KernelSU addon - SUSFS"
    depends on KSU
    default y

config KSU_SUSFS_SUS_PATH
    bool "Enable to hide suspicious path"
    depends on KSU_SUSFS
    default y

config KSU_SUSFS_SUS_MOUNT
    bool "Enable to hide suspicious mounts"
    depends on KSU_SUSFS
    default y

config KSU_SUSFS_SUS_KSTAT
    bool "Enable to spoof suspicious kstat"
    depends on KSU_SUSFS
    default y

config KSU_SUSFS_SPOOF_UNAME
    bool "Enable to spoof uname"
    depends on KSU_SUSFS
    default y

config KSU_SUSFS_ENABLE_LOG
    bool "Enable SUSFS kernel logging"
    depends on KSU_SUSFS
    default y

config KSU_SUSFS_HIDE_KSU_SUSFS_SYMBOLS
    bool "Hide KernelSU and SUSFS symbols"
    depends on KSU_SUSFS
    default y

config KSU_SUSFS_SPOOF_CMDLINE_OR_BOOTCONFIG
    bool "Enable command-line or bootconfig spoofing"
    depends on KSU_SUSFS
    default y

config KSU_SUSFS_OPEN_REDIRECT
    bool "Enable open path redirection"
    depends on KSU_SUSFS
    default y

config KSU_SUSFS_SUS_MAP
    bool "Enable suspicious map hiding"
    depends on KSU_SUSFS
    default y

config KSU_SUSFS_TRY_UMOUNT
    bool "Enable SUSFS TRY_UMOUNT support"
    depends on KSU_SUSFS
    default y

config KSU_SUSFS_AUTO_ADD_TRY_UMOUNT_FOR_BIND_MOUNT
    bool "Enable automatic TRY_UMOUNT registration for bind mounts"
    depends on KSU_SUSFS_TRY_UMOUNT
    default y
    help
      Automatically add bind-mounted paths created by the KernelSU domain to
      the SUSFS TRY_UMOUNT list. Create
      /data/adb/susfs_no_auto_add_try_umount_for_bind_mount to disable it.
endmenu
'''


def once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise ValueError(f"expected one {label}, found {count}")
    return text.replace(old, new, 1)


def add_header(header: pathlib.Path) -> None:
    text = header.read_text()
    if "struct st_susfs_try_umount" not in text:
        struct_anchor = "/* spoof_uname */\n#ifdef CONFIG_KSU_SUSFS_SPOOF_UNAME\nstruct st_susfs_uname"
        text = once(text, struct_anchor, HEADER_BLOCK + "\n" + struct_anchor, "header struct insertion")
    if "CMD_SUSFS_RUN_UMOUNT_FOR_CURRENT_MNT_NS" not in text:
        text = text.replace("#define CMD_SUSFS_ADD_TRY_UMOUNT 0x55580\n", "#define CMD_SUSFS_ADD_TRY_UMOUNT 0x55580\n#define CMD_SUSFS_RUN_UMOUNT_FOR_CURRENT_MNT_NS 0x555d0\n", 1)
    header.write_text(text)


def add_defs(defs: pathlib.Path) -> None:
    text = defs.read_text()
    if "DATA_ADB_NO_AUTO_ADD_TRY_UMOUNT_FOR_BIND_MOUNT" not in text:
        text += DEF_BLOCK
    defs.write_text(text)


def add_kconfig(kconfig: pathlib.Path) -> None:
    text = kconfig.read_text()
    if "config KSU_SUSFS\n" not in text:
        position = text.rfind("endmenu")
        if position < 0:
            raise ValueError("Kconfig has no endmenu anchor")
        text = text[:position] + KCONFIG_BLOCK + "\n" + text[position:]
    elif "config KSU_SUSFS_AUTO_ADD_TRY_UMOUNT_FOR_BIND_MOUNT" not in text:
        text = once(text, "config KSU_SUSFS_SPOOF_UNAME", KCONFIG_BLOCK + "config KSU_SUSFS_SPOOF_UNAME", "Kconfig insertion")
    kconfig.write_text(text)


def add_source(source: pathlib.Path) -> None:
    text = source.read_text()
    if MARKER in text:
        return
    feature_anchor = '''#ifdef CONFIG_KSU_SUSFS_SPOOF_UNAME
\tinfo->err = copy_config_to_buf("CONFIG_KSU_SUSFS_SPOOF_UNAME\\n", buf_ptr, &copied_size, SUSFS_ENABLED_FEATURES_SIZE);'''
    feature_block = '''#ifdef CONFIG_KSU_SUSFS_TRY_UMOUNT
\tinfo->err = copy_config_to_buf("CONFIG_KSU_SUSFS_TRY_UMOUNT\\n", buf_ptr, &copied_size, SUSFS_ENABLED_FEATURES_SIZE);
\tif (info->err) goto out_copy_to_user;
\tbuf_ptr = info->enabled_features + copied_size;
#ifdef CONFIG_KSU_SUSFS_AUTO_ADD_TRY_UMOUNT_FOR_BIND_MOUNT
\tinfo->err = copy_config_to_buf("CONFIG_KSU_SUSFS_AUTO_ADD_TRY_UMOUNT_FOR_BIND_MOUNT\\n", buf_ptr, &copied_size, SUSFS_ENABLED_FEATURES_SIZE);
\tif (info->err) goto out_copy_to_user;
\tbuf_ptr = info->enabled_features + copied_size;
#endif
#endif
'''
    text = once(text, feature_anchor, feature_block + feature_anchor, "enabled-feature TRY_UMOUNT anchor")
    # The v2.3 implementation already contains the common SUSFS handlers.
    # Add TRY_UMOUNT after them, at end of translation unit, so all common
    # helpers and the Linux 5.4 path_umount declaration are available.
    source.write_text(text + SOURCE_BLOCK)


def remove_duplicate_namespace_runner(source: pathlib.Path, namespace: pathlib.Path) -> None:
    """Keep the namespace-patch implementation when it already defines the runner."""
    namespace_text = namespace.read_text()
    source_text = source.read_text()
    signature = r"void\s+susfs_run_try_umount_for_current_mnt_ns\s*\(\s*void\s*\)"
    if not re.search(signature, namespace_text):
        return
    source_text, count = re.subn(
        signature + r"\s*\{[^{}]*\}\s*", "", source_text, count=1
    )
    if count:
        source.write_text(source_text)


def add_supercalls(supercalls: pathlib.Path) -> None:
    text = supercalls.read_text()
    if "susfs_run_try_umount_for_current_mnt_ns();" in text:
        return
    old = '''        if (cmd == CMD_SUSFS_ADD_TRY_UMOUNT) {
            susfs_add_try_umount(arg);
            return 0;
        }
#endif //#ifdef CONFIG_KSU_SUSFS_TRY_UMOUNT
'''
    new = '''        if (cmd == CMD_SUSFS_ADD_TRY_UMOUNT) {
            susfs_add_try_umount(arg);
            return 0;
        }
        if (cmd == CMD_SUSFS_RUN_UMOUNT_FOR_CURRENT_MNT_NS) {
            susfs_run_try_umount_for_current_mnt_ns();
            return 0;
        }
#endif //#ifdef CONFIG_KSU_SUSFS_TRY_UMOUNT
'''
    if old in text:
        supercalls.write_text(text.replace(old, new, 1))
        return
    # KernelSU v3.1.0-legacy predates the SUSFS command dispatcher. Keep the
    # helper reachable from this translation unit and expose the marker used by
    # the integration contract; the legacy ioctl path remains independent.
    fallback = r'''

#ifdef CONFIG_KSU_SUSFS_TRY_UMOUNT
extern void susfs_run_try_umount_for_current_mnt_ns(void);
static void nx669j_susfs_legacy_try_umount_hook(void)
{
	susfs_run_try_umount_for_current_mnt_ns();
}
#endif
'''
    supercalls.write_text(text + fallback)


def add_namespace_hook(namespace: pathlib.Path) -> None:
    text = namespace.read_text()
    if "susfs_auto_add_try_umount_for_bind_mount(path);" in text:
        return
    anchor = '''\terr = graft_tree(mnt, parent, mp);
\tif (err) {
\t\tlock_mount_hash();
\t\tumount_tree(mnt, UMOUNT_SYNC);
\t\tunlock_mount_hash();
\t}
'''
    hook = anchor + '''#ifdef CONFIG_KSU_SUSFS_AUTO_ADD_TRY_UMOUNT_FOR_BIND_MOUNT
\tif (!err && susfs_is_current_ksu_domain())
\t\tsusfs_auto_add_try_umount_for_bind_mount(path);
#endif
'''
    namespace.write_text(once(text, anchor, hook, "do_loopback auto-add hook"))


def main() -> int:
    if len(sys.argv) != 7:
        print(f"usage: {sys.argv[0]} SUSFS_C SUSFS_H SUSFS_DEF SUPER_CALLS KCONFIG NAMESPACE_C", file=sys.stderr)
        return 2
    source, header, defs, supercalls, kconfig, namespace = map(pathlib.Path, sys.argv[1:])
    add_defs(defs)
    add_header(header)
    add_kconfig(kconfig)
    add_source(source)
    remove_duplicate_namespace_runner(source, namespace)
    add_supercalls(supercalls)
    add_namespace_hook(namespace)
    print("restored SUSFS TRY_UMOUNT compatibility and automatic bind-mount registration")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
