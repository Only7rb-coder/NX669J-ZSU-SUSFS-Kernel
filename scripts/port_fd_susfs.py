#!/usr/bin/env python3
"""Port the SUSFS mount-hiding fd-info hunk to the NX669J vendor tree."""
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: port_fd_susfs.py /path/to/fs/proc/fd.c")

path = Path(sys.argv[1])
text = path.read_text()
old = '''\tseq_printf(m, "pos:\\t%lli\\nflags:\\t0%o\\nmnt_id:\\t%i\\n",
\t\t   (long long)file->f_pos, f_flags,
\t\t   real_mount(file->f_path.mnt)->mnt_id);
'''
new = '''#ifdef CONFIG_KSU_SUSFS_SUS_MOUNT
\tmnt = real_mount(file->f_path.mnt);
\tif (likely(current->susfs_task_state & TASK_STRUCT_NON_ROOT_USER_APP_PROC) &&
\t\t\tmnt->mnt_id >= DEFAULT_SUS_MNT_ID) {
\t\tstruct path path;
\t\tchar *pathname = kmalloc(PAGE_SIZE, GFP_KERNEL);
\t\tchar *dpath;

\t\tfor (; mnt->mnt_id >= DEFAULT_SUS_MNT_ID; mnt = mnt->mnt_parent) { }

\t\tif (!pathname)
\t\t\tgoto out_seq_printf;
\t\tdpath = d_path(&file->f_path, pathname, PAGE_SIZE);
\t\tif (!dpath)
\t\t\tgoto out_free_pathname;
\t\tif (kern_path(dpath, 0, &path))
\t\t\tgoto out_free_pathname;
\t\tseq_printf(m, "pos:\\t%lli\\nflags:\\t0%o\\nmnt_id:\\t%i\\n",
\t\t\t\t(long long)file->f_pos, f_flags, mnt->mnt_id);
\t\tpath_put(&path);
\t\tkfree(pathname);
\t\tgoto bypass_orig_flow;
out_free_pathname:
\t\tkfree(pathname);
\t}
out_seq_printf:
\tseq_printf(m, "pos:\\t%lli\\nflags:\\t0%o\\nmnt_id:\\t%i\\n",
\t\t   (long long)file->f_pos, f_flags, mnt->mnt_id);
\tbypass_orig_flow:
#else
\tseq_printf(m, "pos:\\t%lli\\nflags:\\t0%o\\nmnt_id:\\t%i\\n",
\t\t   (long long)file->f_pos, f_flags,
\t\t   real_mount(file->f_path.mnt)->mnt_id);
#endif
'''
if text.count(old) != 1:
    raise SystemExit("expected original fd-info seq_printf block exactly once")
path.write_text(text.replace(old, new))
print(f"Ported SUSFS fd-info hunk in {path}")
