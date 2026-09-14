#!/usr/bin/env python3
from __future__ import annotations
import argparse, shutil, time
from pathlib import Path
BEGIN='<!-- EUROGAS_ARCH_V2_AUTONOMY_BEGIN -->'
END='<!-- EUROGAS_ARCH_V2_AUTONOMY_END -->'
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--repo',required=True);a=ap.parse_args();repo=Path(a.repo).expanduser().resolve()
    src=repo/'AGENTS_ARCHITECTURE_V2_APPEND.md';dst=repo/'AGENTS.md'
    if not src.exists():raise SystemExit(f'Missing {src}; run INSTALL_TO_REPO.py first.')
    block=src.read_text(encoding='utf-8').strip();old=dst.read_text(encoding='utf-8') if dst.exists() else ''
    if BEGIN in old and END in old:
        before=old.split(BEGIN,1)[0].rstrip();after=old.split(END,1)[1].lstrip();new=(before+'\n\n'+block+'\n\n'+after).strip()+'\n'
    else:new=(old.rstrip()+'\n\n'+block+'\n').lstrip()
    if dst.exists() and dst.read_text(encoding='utf-8')!=new:
        backup=dst.with_name(f'AGENTS.md.backup-{time.strftime("%Y%m%d-%H%M%S")}');shutil.copy2(dst,backup);print('Backup:',backup)
    dst.write_text(new,encoding='utf-8');print('Merged Architecture V2 autonomy rules into',dst)
if __name__=='__main__':main()
