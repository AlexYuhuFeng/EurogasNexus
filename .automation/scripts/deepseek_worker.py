#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,os,subprocess,time
from pathlib import Path
from common import repo_root,load_toml,extract_thread_id,classify_output,kill_process_tree,save_json,resolve_executable

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--task-file',required=True);a=ap.parse_args();root=repo_root();cfg=load_toml(root/'.automation'/'config.toml');wc=cfg['worker']
    if not os.environ.get('DEEPSEEK_API_KEY'):raise SystemExit('DEEPSEEK_API_KEY is not set')
    tf=(root/a.task_file).resolve() if not Path(a.task_file).is_absolute() else Path(a.task_file).resolve();tasks=(root/'.automation'/'runtime'/'tasks').resolve()
    if not tf.exists() or tasks not in tf.parents:raise SystemExit('Task file must exist under .automation/runtime/tasks')
    home=root/'.automation'/'runtime'/'codex-deepseek-home';prefix=(root/'.automation'/'prompts'/'deepseek_worker_prefix.md').read_text(encoding='utf-8');prompt=prefix+'\n'+tf.read_text(encoding='utf-8')
    rd=root/'.automation'/'runtime'/'worker_runs';rd.mkdir(parents=True,exist_ok=True);stamp=time.strftime('%Y%m%d-%H%M%S');stem=tf.stem+'-'+stamp;events=rd/(stem+'.jsonl');errp=rd/(stem+'.stderr.log');final=rd/(stem+'.final.json')
    cmd=[resolve_executable(cfg['codex']['binary']),'exec','--json','--color','never','--sandbox',wc['sandbox_mode'],'-C',str(root),'-m',wc['model'],'-c',f'approval_policy="{wc["approval_policy"]}"','-c',f'model_reasoning_effort="{wc["reasoning_effort"]}"','-c','agents.enabled=false','-c','features.plugins=false','--output-schema',str(root/'.automation'/'schemas'/'worker_output.schema.json'),'-o',str(final),prompt]
    env=os.environ.copy();env['CODEX_HOME']=str(home);flags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name=='nt' else 0;proc=subprocess.Popen(cmd,cwd=root,env=env,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',errors='replace',creationflags=flags,start_new_session=(os.name!='nt'))
    try:out,err=proc.communicate(timeout=int(wc['turn_timeout_seconds']))
    except subprocess.TimeoutExpired:kill_process_tree(proc);out,err=proc.communicate();err+='\nWORKER_TIMEOUT\n'
    events.write_text(out,encoding='utf-8');errp.write_text(err,encoding='utf-8');cls=classify_output(out+'\n'+err,proc.returncode);meta={"task_file":str(tf.relative_to(root)),"returncode":proc.returncode,"classification":cls,"thread_id":extract_thread_id(out),"events":str(events.relative_to(root)),"stderr":str(errp.relative_to(root)),"final":str(final.relative_to(root)) if final.exists() else None};mp=rd/(stem+'.meta.json');save_json(mp,meta);print(json.dumps({"meta":str(mp.relative_to(root)),**meta},ensure_ascii=False));return 0 if proc.returncode==0 and cls=='success' else 1
if __name__=='__main__':raise SystemExit(main())
