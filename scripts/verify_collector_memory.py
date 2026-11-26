#!/usr/bin/env python3
"""Local concurrent manual capture probe; never call a model or admit a case."""
import datetime as dt
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.experiment_runtime import KUBE


def request(path,post=False):
    req=urllib.request.Request('http://127.0.0.1:8000'+path,data=b'{}' if post else None,
        headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=15) as response:return json.load(response)


def pod_state():
    pod=json.loads(subprocess.check_output(KUBE+['-n','monitoring','get','pod','-l','app=incident-collector','-o','json']))['items']
    if len(pod)!=1:raise RuntimeError('Exactly one collector Pod expected')
    p=pod[0];s=p['status']['containerStatuses'][0]
    return {'uid':p['metadata']['uid'],'ready':s['ready'],'restart_count':s['restartCount']}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path);args=parser.parse_args()
    directory=ROOT/Path((ROOT/'.runtime/collector-recovery-path').read_text().strip())
    output=args.output or directory/'concurrent-capture-verification.json'
    if output.exists():raise ValueError('Never replace a verification result')
    result={'started_at':dt.datetime.now(dt.timezone.utc).isoformat(),'status':'started','manual_development_only':True,
        'cloud_called':False,'ids':[],'samples':[],'errors':[]}
    def save():output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    try:
        result['before']=pod_state();save()
        if not result['before']['ready']:raise RuntimeError('Collector not ready')
        if request('/health')['status']!='ok':raise RuntimeError('Collector tunnel not healthy')
        for _ in range(3):result['ids'].append(request('/incidents/manual',True)['incident_id']);save()
        deadline=time.monotonic()+300
        while time.monotonic()<deadline:
            pod=pod_state();sample={'at':dt.datetime.now(dt.timezone.utc).isoformat(),'pod':pod,'health':request('/health')}
            raw=subprocess.check_output(KUBE+['-n','monitoring','exec','deployment/incident-collector','--','cat',
                '/sys/fs/cgroup/memory.current','/sys/fs/cgroup/memory.peak'],text=True).split()
            sample.update(memory_current_bytes=int(raw[0]),memory_peak_bytes=int(raw[1]));result['samples'].append(sample)
            if pod!=result['before']:raise RuntimeError('Collector readiness, UID or restart counter changed')
            reports=[request('/incidents/'+key) for key in result['ids']];result['incidents']=reports;save()
            if all(r['status'] not in ('queued','collecting') for r in reports):break
            time.sleep(10)
        if not all(r['status']=='captured' for r in result['incidents']):
            raise RuntimeError('Manual source capture incomplete; inspect preserved incident manifests')
        for row in result['incidents']:
            manifest=row['manifest']
            if abs(manifest['window_end']-manifest['window_start']-150)>.01:
                raise RuntimeError('Observation window changed by queueing')
        result['status']='passed_three_serialized_manual_captures'
    except Exception as exc:
        result['status']='failed';result['errors'].append(type(exc).__name__+': '+str(exc))
    result['finished_at']=dt.datetime.now(dt.timezone.utc).isoformat();save()
    print(json.dumps({'status':result['status'],'proof':str(output),'errors':result['errors']},ensure_ascii=False))
    return 0 if result['status'].startswith('passed') else 1


if __name__=='__main__':raise SystemExit(main())
