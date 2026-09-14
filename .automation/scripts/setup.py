#!/usr/bin/env python3
from __future__ import annotations
import argparse, os, shutil, subprocess, sys
from common import repo_root, load_toml, codex_version, MIN_CODEX, save_json

def create_worker_home(root,model):
    home=root/'.automation'/'runtime'/'codex-deepseek-home'; home.mkdir(parents=True,exist_ok=True)
    shutil.copy2(root/'.automation'/'codex'/'deepseek_model_catalog.json',home/'models.json')
    cfg = f'''model = "{model}"
model_provider = "deepseek"
model_reasoning_effort = "high"
model_catalog_json = "{(home/'models.json').as_posix()}"
approval_policy = "never"
sandbox_mode = "workspace-write"

[model_providers.deepseek]
name = "deepseek"
base_url = "https://api.deepseek.com/"
env_key = "DEEPSEEK_API_KEY"
wire_api = "responses"
requires_openai_auth = false
'''
    (home/'config.toml').write_text(cfg,encoding='utf-8'); return home

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--prepare-branch',action='store_true'); ap.add_argument('--force-branch',action='store_true'); a=ap.parse_args()
    root=repo_root(); cfg=load_toml(root/'.automation'/'config.toml'); ver,raw=codex_version(cfg['codex']['binary']); print('Repo:',root); print('Codex:',raw or 'NOT FOUND')
    if not ver or ver<MIN_CODEX:print('ERROR: Codex CLI 0.153.0+ required.',file=sys.stderr);return 2
    if a.prepare_branch:
        dirty=subprocess.check_output(['git','-C',str(root),'status','--porcelain'],text=True).strip(); branch=cfg['project']['required_branch']; current=subprocess.check_output(['git','-C',str(root),'branch','--show-current'],text=True).strip()
        if current!=branch:
            exists=subprocess.run(['git','-C',str(root),'show-ref','--verify','--quiet',f'refs/heads/{branch}']).returncode==0
            if exists and dirty and not a.force_branch:
                print('ERROR: target branch already exists and working tree is dirty; commit/stash first or use --force-branch only after manual review.',file=sys.stderr);return 2
            # Creating a new branch preserves the just-installed uncommitted runner files and is safe.
            subprocess.check_call(['git','-C',str(root),'switch',branch] if exists else ['git','-C',str(root),'switch','-c',branch])
    home=create_worker_home(root,cfg['worker']['model']); runtime=root/'.automation'/'runtime'; (runtime/'tasks').mkdir(parents=True,exist_ok=True); (runtime/'worker_runs').mkdir(exist_ok=True); (root/'.automation'/'logs').mkdir(parents=True,exist_ok=True)
    cp=runtime/'control.json'
    if not cp.exists():save_json(cp,{"status":"RUNNING","active_node_id":cfg['automation']['active_node_id'],"astra_thread_id":None,"astra_resume_count":0,"last_worker_result":None,"last_error":None})
    if not os.environ.get('DEEPSEEK_API_KEY'):print('WARNING: DEEPSEEK_API_KEY not visible in this process.')
    print('DeepSeek worker home:',home); print('Next: python .automation/scripts/preflight.py'); return 0
if __name__=='__main__':raise SystemExit(main())
