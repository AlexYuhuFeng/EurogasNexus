#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,os,subprocess,sys,time
from pathlib import Path
from common import repo_root,load_toml,load_json,save_json,classify_output,parse_reset_epoch,extract_thread_id,kill_process_tree,git,resolve_executable

def log(root,msg):
    line=f'{time.strftime("%Y-%m-%d %H:%M:%S")} {msg}';print(line,flush=True);p=root/'.automation'/'logs'/'supervisor.log';p.parent.mkdir(parents=True,exist_ok=True);p.open('a',encoding='utf-8').write(line+'\n')

def lock(root):
    p=root/'.automation'/'runtime'/'supervisor.lock';p.parent.mkdir(parents=True,exist_ok=True);f=p.open('a+')
    try:
        if os.name=='nt':
            import msvcrt;f.seek(0);msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl;fcntl.flock(f.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
    except Exception:f.close();raise RuntimeError('Another supervisor is active for this working tree')
    return f

def prompt(root,ctx):return (root/'.automation'/'prompts'/'orchestrator_slice.md').read_text(encoding='utf-8').replace('{{RECOVERY_CONTEXT}}',ctx or 'No extra context.')

def run_astra(root,cfg,control,text):
    c=cfg['codex'];rd=root/'.automation'/'runtime'/'astra_runs';rd.mkdir(parents=True,exist_ok=True);stamp=time.strftime('%Y%m%d-%H%M%S');events=rd/(stamp+'.jsonl');errp=rd/(stamp+'.stderr.log');final=rd/(stamp+'.final.json');tid=control.get('astra_thread_id');resume=bool(c['resume_session'] and tid and control.get('astra_resume_count',0)<c['max_resumes_per_session'])
    exe=resolve_executable(c['binary'])
    if resume:cmd=[exe,'exec','--json','--color','never','-c',f'sandbox_mode="{c["sandbox_mode"]}"','-c',f'approval_policy="{c["approval_policy"]}"','-c',f'model_reasoning_effort="{c["reasoning_effort"]}"','-c','features.plugins=false','--output-schema',str(root/'.automation'/'schemas'/'orchestrator_output.schema.json'),'-o',str(final),'resume',tid,text]
    else:cmd=[exe,'exec','--json','--color','never','--sandbox',c['sandbox_mode'],'-C',str(root),'-m',c['model'],'-c',f'approval_policy="{c["approval_policy"]}"','-c',f'model_reasoning_effort="{c["reasoning_effort"]}"','-c','features.plugins=false','--output-schema',str(root/'.automation'/'schemas'/'orchestrator_output.schema.json'),'-o',str(final),text]
    flags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name=='nt' else 0;proc=subprocess.Popen(cmd,cwd=root,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',errors='replace',creationflags=flags,start_new_session=(os.name!='nt'))
    try:out,err=proc.communicate(timeout=int(c['turn_timeout_seconds']))
    except subprocess.TimeoutExpired:kill_process_tree(proc);out,err=proc.communicate();err+='\nASTRA_TURN_TIMEOUT\n'
    events.write_text(out,encoding='utf-8');errp.write_text(err,encoding='utf-8');new=extract_thread_id(out)
    if resume and new and new!=tid:log(root,f'WARNING resume id mismatch requested={tid} returned={new}');control['astra_thread_id']=new;control['astra_resume_count']=0
    elif new:control['astra_thread_id']=new;control['astra_resume_count']=control.get('astra_resume_count',0)+1 if resume else 0
    result=None
    if final.exists():
        try:result=json.loads(final.read_text(encoding='utf-8'))
        except Exception as e:log(root,f'Invalid Astra final JSON: {e}')
    return classify_output(out+'\n'+err,proc.returncode),proc.returncode,out,err,result,str(events.relative_to(root)),str(final.relative_to(root)) if final.exists() else None

def allowance_probe(root,cfg):
    c=cfg['codex'];exe=resolve_executable(c['binary']);p=subprocess.run([exe,'exec','--color','never','--sandbox','read-only','-C',str(root),'-m',c['model'],'-c','approval_policy="never"','-c',f'model_reasoning_effort="{c["reasoning_effort"]}"','-c','features.plugins=false','Do not read or modify files. Reply exactly READY.'],cwd=root,stdin=subprocess.DEVNULL,text=True,encoding='utf-8',errors='replace',capture_output=True,timeout=900);t=(p.stdout or '')+'\n'+(p.stderr or '');return p.returncode==0 and 'READY' in t and classify_output(t,p.returncode)!='allowance',t

def wait_allowance(root,cfg,text,once):
    if once:log(root,'Allowance hit in --once mode; exiting.');return False
    a=cfg['allowance'];reset=parse_reset_epoch(text);now=time.time()
    if reset and reset>now and reset-now<=a['max_parsed_wait_seconds']:
        secs=max(a['minimum_wait_seconds'],int(reset-now)+a['reset_grace_seconds']);log(root,f'Parsed reset; sleeping about {secs//60} minutes.');time.sleep(secs)
    else:log(root,f'No trusted reset time; sleeping {a["probe_interval_seconds"]//60} minutes.');time.sleep(a['probe_interval_seconds'])
    while True:
        ok,_=allowance_probe(root,cfg)
        if ok:log(root,'Allowance available; resuming.');return True
        log(root,'Allowance still unavailable.');time.sleep(a['probe_interval_seconds'])

def run_worker(root,tf):
    p=subprocess.run([sys.executable,str(root/'.automation'/'scripts'/'deepseek_worker.py'),'--task-file',str(tf.relative_to(root))],cwd=root,stdin=subprocess.DEVNULL,text=True,encoding='utf-8',errors='replace',capture_output=True);meta=None
    for line in reversed((p.stdout or '').splitlines()):
        try:o=json.loads(line);meta=o if 'meta' in o else meta
        except Exception:pass
    return p.returncode,(p.stdout or '')+'\n'+(p.stderr or ''),meta

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--once',action='store_true');a=ap.parse_args();root=repo_root();cfg=load_toml(root/'.automation'/'config.toml');_lock=lock(root);cp=root/'.automation'/'runtime'/'control.json';control=load_json(cp,{}) or {};node=os.environ.get('EUROGAS_ORCHESTRATOR_NODE_ID','windows-primary')
    if control.get('active_node_id',cfg['automation']['active_node_id'])!=node:log(root,f'Node {node} standby; active={control.get("active_node_id")}');return 0
    branch=git(['branch','--show-current'],root).stdout.strip()
    if cfg['project']['enforce_required_branch'] and branch!=cfg['project']['required_branch']:log(root,f'FATAL wrong branch {branch}');return 2
    recovery='Fresh orchestration cycle.';fails=0
    while True:
        if (root/'.automation'/'STOP').exists():log(root,'STOP file present.');return 0
        control=load_json(cp,control) or control
        if control.get('status') in {'WAITING_HUMAN','COMPLETE','STOPPED'}:log(root,f'Control={control.get("status")}; exiting.');return 0
        cls,rc,out,err,res,ev,fin=run_astra(root,cfg,control,prompt(root,recovery));control['last_astra_events']=ev;control['last_astra_final']=fin;save_json(cp,control)
        if cls=='allowance':
            control['status']='WAITING_ALLOWANCE';control['last_error']='Astra allowance exhausted';save_json(cp,control)
            if not wait_allowance(root,cfg,out+'\n'+err,a.once):return 3
            control['status']='RUNNING';save_json(cp,control);recovery=(root/'.automation'/'prompts'/'recovery.md').read_text(encoding='utf-8');continue
        if cls=='transient':
            fails+=1;log(root,f'Transient Astra failure {fails}')
            if fails>=cfg['loop']['max_consecutive_failures']:control['status']='WAITING_HUMAN';control['last_error']='Repeated transient Astra failures';save_json(cp,control);return 4
            if a.once:return 4
            time.sleep(cfg['loop']['transient_retry_seconds']);recovery='Retry after transient failure; inspect disk first.';continue
        if cls!='success' or not isinstance(res,dict):control['status']='WAITING_HUMAN';control['last_error']=f'Astra failure {cls} rc={rc}';save_json(cp,control);return 5
        fails=0;action=res['action'];log(root,f'Astra action={action}; review={res.get("review_outcome")}; {res.get("reason")}')
        if action=='wait_human':control['status']='WAITING_HUMAN';control['last_error']=res.get('reason');save_json(cp,control);return 0
        if action=='complete':control['status']='COMPLETE';save_json(cp,control);return 0
        if action=='delegate':
            raw=res.get('task_file');tf=(root/raw).resolve() if raw else None;taskroot=(root/'.automation'/'runtime'/'tasks').resolve()
            if not tf or not tf.exists() or taskroot not in tf.parents:control['status']='WAITING_HUMAN';control['last_error']='Invalid delegated task path';save_json(cp,control);return 6
            wrc,wtext,wmeta=run_worker(root,tf);control['last_worker_result']=wmeta;save_json(cp,control)
            if wrc:recovery=f'Worker failed for {tf.relative_to(root)}. Inspect diff and worker metadata {wmeta}; decide rework or human gate.'
            else:recovery=f'Worker completed {tf.relative_to(root)}. Inspect actual diff and worker metadata {wmeta}; accept/rework then choose next bounded task.'
        else:recovery='Continue from checkpoint and current diff.'
        if a.once:return 0
        time.sleep(cfg['loop']['success_sleep_seconds'])
if __name__=='__main__':raise SystemExit(main())
