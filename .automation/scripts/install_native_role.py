#!/usr/bin/env python3
from __future__ import annotations
import argparse,os,shutil,time
from pathlib import Path
from common import repo_root
BLOCK='''\n# --- EUROGAS DEEPSEEK NATIVE ROLE BEGIN ---\n[model_providers.deepseek]\nname = "deepseek"\nbase_url = "https://api.deepseek.com/"\nenv_key = "DEEPSEEK_API_KEY"\nwire_api = "responses"\nrequires_openai_auth = false\n\n[agents.deepseek_worker]\ndescription = "Bounded Eurogas Nexus implementation worker using DeepSeek Flash V4.1."\nconfig_file = "agents/eurogas-deepseek-worker.toml"\n# --- EUROGAS DEEPSEEK NATIVE ROLE END ---\n'''
def main():
    p=argparse.ArgumentParser();p.add_argument('--yes',action='store_true');a=p.parse_args()
    if not a.yes:print('Read README_FIRST.md, then re-run with --yes.');return 2
    root=repo_root();home=Path(os.environ.get('CODEX_HOME',Path.home()/'.codex')).expanduser();home.mkdir(parents=True,exist_ok=True);cfg=home/'config.toml';old=cfg.read_text(encoding='utf-8') if cfg.exists() else ''
    if 'EUROGAS DEEPSEEK NATIVE ROLE BEGIN' not in old:
        if cfg.exists():shutil.copy2(cfg,cfg.with_suffix(f'.toml.backup-{time.strftime("%Y%m%d-%H%M%S")}'))
        cfg.write_text(old.rstrip()+BLOCK+'\n',encoding='utf-8')
    agents=home/'agents';agents.mkdir(exist_ok=True);catalog=home/'eurogas-deepseek-models.json';shutil.copy2(root/'.automation'/'codex'/'deepseek_model_catalog.json',catalog);(agents/'eurogas-deepseek-worker.toml').write_text(f'model = "deepseek-flash"\nmodel_provider = "deepseek"\nmodel_reasoning_effort = "high"\nmodel_catalog_json = "{catalog.as_posix()}"\n',encoding='utf-8');print('Optional native role installed. Restart Codex, smoke-test manually, and keep bridge mode until verified.');return 0
if __name__=='__main__':raise SystemExit(main())
