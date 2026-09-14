#!/usr/bin/env python3
import argparse
from common import repo_root,load_json,save_json
p=argparse.ArgumentParser();p.add_argument('status',choices=['RUNNING','WAITING_HUMAN','COMPLETE','STOPPED','WAITING_ALLOWANCE']);p.add_argument('--active-node');a=p.parse_args();root=repo_root();f=root/'.automation'/'runtime'/'control.json';d=load_json(f,{}) or {};d['status']=a.status
if a.active_node:d['active_node_id']=a.active_node
save_json(f,d);print(d)
