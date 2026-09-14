#!/usr/bin/env python3
from __future__ import annotations
import argparse, os, shutil, subprocess, sys
from common import repo_root, load_toml, codex_version, MIN_CODEX, git, classify_output, resolve_executable

def probe_worker(root,cfg):
    wc=cfg['worker']; home=root/'.automation'/'runtime'/'codex-deepseek-home'
    env=os.environ.copy(); env['CODEX_HOME']=str(home)
    marker='DEEPSEEK_WORKER_READY'
    cmd=[resolve_executable(cfg['codex']['binary']),'exec','--color','never','--sandbox','read-only','-C',str(root),'-m',wc['model'],
         '-c','approval_policy="never"','-c',f'model_reasoning_effort="{wc["reasoning_effort"]}"','-c','agents.enabled=false',
         '-c','features.plugins=false',f'Do not read or modify repository files. Reply exactly {marker}.']
    try:
        p=subprocess.run(cmd,cwd=root,env=env,stdin=subprocess.DEVNULL,text=True,encoding='utf-8',errors='replace',capture_output=True,timeout=900)
    except Exception as e:
        return False,f'worker probe failed to launch: {e}'
    stdout=(p.stdout or '')
    stderr=(p.stderr or '')
    text=stdout+'\n'+stderr
    probe_dir=root/'.automation'/'runtime'/'probe'
    probe_dir.mkdir(parents=True,exist_ok=True)
    (probe_dir/'deepseek-probe.stdout.log').write_text(stdout,encoding='utf-8')
    (probe_dir/'deepseek-probe.stderr.log').write_text(stderr,encoding='utf-8')
    ok=p.returncode==0 and marker in text and classify_output(text,p.returncode)=='success'
    if ok:
        return True,'DeepSeek worker probe OK'
    return False,(f'DeepSeek worker probe failed rc={p.returncode}. '
                  f'Inspect .automation/runtime/probe/deepseek-probe.stderr.log and '
                  f'.automation/runtime/probe/deepseek-probe.stdout.log.')

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--probe-worker',action='store_true',help='make one tiny DeepSeek call through the isolated Codex worker runtime');a=ap.parse_args()
    root=repo_root();cfg=load_toml(root/'.automation'/'config.toml');errs=[];warns=[];ver,raw=codex_version(cfg['codex']['binary']);print('Codex:',raw)
    if not ver:errs.append('Codex CLI not found')
    elif ver<MIN_CODEX:errs.append(f'Codex {ver} older than {MIN_CODEX}')
    if sys.version_info<(3,11):errs.append('Python 3.11+ required')
    if shutil.which('git') is None:errs.append('git not found')
    branch=git(['branch','--show-current'],root).stdout.strip();print('Branch:',branch)
    if cfg['project']['enforce_required_branch'] and branch!=cfg['project']['required_branch']:errs.append(f'Expected branch {cfg["project"]["required_branch"]}')
    if git(['status','--porcelain'],root).stdout.strip():warns.append('Working tree is not clean; inspect/commit before unattended mode')
    if not os.environ.get('DEEPSEEK_API_KEY'):errs.append('DEEPSEEK_API_KEY not set')
    for p in (root/'docs'/'engineering'/'Architecture-V2'/'CODEX_ENTRYPOINT.md',root/'docs'/'engineering'/'ARCHITECTURE_V2_EXECUTION_STATE.md',root/'.automation'/'runtime'/'codex-deepseek-home'/'config.toml'):
        if not p.exists():errs.append(f'Missing {p}')
    print('Warnings:');[print(' -',x) for x in warns];print('Errors:');[print(' -',x) for x in errs]
    if errs:return 2
    if a.probe_worker:
        ok,msg=probe_worker(root,cfg);print(msg)
        if not ok:return 3
    print('PRECHECK OK');return 0
if __name__=='__main__':raise SystemExit(main())
