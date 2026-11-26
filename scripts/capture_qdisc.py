#!/usr/bin/env python3
"""Read network counters for the frontend Pod in this dedicated testbed only."""
import datetime
import json
import os
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parents[1]


def capture_qdisc(destination,source='front-end'):
    if source not in ('front-end','orders'):raise ValueError('Source outside supported network edges')
    env=dict(os.environ,MINIKUBE_HOME=str(ROOT/'.runtime/minikube'))
    command=['kubectl','--kubeconfig',str(ROOT/'.runtime/kubeconfig'),'--context','shyn-thesis',
             '-n','sock-shop','get','pods','-l','name='+source,'-o','json']
    pods=json.loads(subprocess.check_output(command,text=True,timeout=20))['items']
    if len(pods)!=1: raise RuntimeError('Expected exactly one source Pod')
    container=pods[0]['status']['containerStatuses'][0]['containerID'].removeprefix('containerd://')
    if not re.fullmatch('[a-f0-9]{64}',container): raise ValueError('Unexpected container ID')
    prefix=['minikube','-p','shyn-thesis','ssh','--']
    inspect=json.loads(subprocess.check_output(prefix+[
        'sudo crictl --runtime-endpoint=unix:///run/containerd/containerd.sock inspect '+container],
        env=env,text=True,timeout=30))
    pid=int(inspect['info']['pid'])
    if pid<1: raise ValueError('Invalid container PID')
    raw=subprocess.check_output(prefix+[f'sudo nsenter -t {pid} -n -- tc -s qdisc show dev eth0'],
                                env=env,text=True,timeout=30)
    drops=[int(value) for value in re.findall(r'dropped\s+(\d+)',raw)]
    output={'checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'pod':pods[0]['metadata']['name'],'pod_uid':pods[0]['metadata']['uid'],
            'dropped_counts':drops,'max_reported_drops':max(drops,default=0),'raw_qdisc':raw,
            'role':'ground_truth_verification_only_not_llm_context'}
    Path(destination).write_text(json.dumps(output,indent=2)+'\n')
    return output
