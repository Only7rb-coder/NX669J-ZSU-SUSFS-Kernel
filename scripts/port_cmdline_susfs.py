#!/usr/bin/env python3
"""Port SUSFS command-line spoofing to a non-GKI procfs cmdline file."""
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: port_cmdline_susfs.py /path/to/fs/proc/cmdline.c")

path = Path(sys.argv[1])
text = path.read_text()
old = '''#include <linux/seq_file.h>

static int cmdline_proc_show(struct seq_file *m, void *v)
{
\tseq_puts(m, saved_command_line);
'''
new = '''#include <linux/seq_file.h>

#ifdef CONFIG_KSU_SUSFS_SPOOF_CMDLINE_OR_BOOTCONFIG
extern int susfs_spoof_cmdline_or_bootconfig(struct seq_file *m);
#endif

static int cmdline_proc_show(struct seq_file *m, void *v)
{
#ifdef CONFIG_KSU_SUSFS_SPOOF_CMDLINE_OR_BOOTCONFIG
\tif (!susfs_spoof_cmdline_or_bootconfig(m))
\t\treturn 0;
#endif
\tseq_puts(m, saved_command_line);
'''
if text.count(old) != 1:
    raise SystemExit("expected original proc cmdline block exactly once")
path.write_text(text.replace(old, new))
print(f"Ported SUSFS command-line spoofing in {path}")
