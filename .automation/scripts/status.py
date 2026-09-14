#!/usr/bin/env python3
from common import repo_root,load_json,git
root=repo_root();print('Repo:',root);print('Branch:',git(['branch','--show-current'],root).stdout.strip());print('Control:',load_json(root/'.automation'/'runtime'/'control.json',{}));print('STOP:',(root/'.automation'/'STOP').exists())
