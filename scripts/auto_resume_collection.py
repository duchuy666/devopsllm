#!/usr/bin/env python3
"""Resume the collection only after one specific, diagnosed-benign stop; everything else waits for a human.

Benign stop = the next preflight failed with "Pod identity/restarts changed since soak" AND every container
restart since that batch's soak is an OOMKilled of the previous captured attempt's own memory-fault target,
finished between its injection and cleanup (+60 s); no Pod was replaced; no chaos object remains; all
sock-shop Pods are Ready. The resume runs a fresh 600 s soak before any scenario, as the protocol requires.
Each decision is appended to results/dataset-collection/<journal>/auto-resume.json. Operator rule adopted
2026-11-26 for the submission deadline.
"""
import argparse
import datetime as dt
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
KUBE=['kubectl','--kubeconfig',str(ROOT/'.runtime/kubeconfig')]


def kubectl_json(*args):
    return json.loads(subprocess.run(KUBE+list(args)+['-o','json'],capture_output=True,text=True,check=True,timeout=60).stdout)


def benign(journal,root=ROOT,pods=None,chaos=None):
    """Return (True, detail) only for the OOM-in-target case; (False, reason) otherwise."""
    if journal.get('status')!='stopped_requires_review':return False,'not stopped'
    attempts=journal['attempts']
    if len(attempts)<2:return False,'no previous attempt'
    last,prev=attempts[-1],attempts[-2]
    if last.get('status')!='preflight_failed':return False,'last attempt is not a preflight failure'
    ground=json.loads((root/last['candidate_paths'][0]/'ground-truth.json').read_text())
    if ground.get('error')!='Pod identity/restarts changed since soak':return False,'preflight reason differs'
    if prev.get('status')!='captured_requires_review':return False,'previous attempt not captured'
    before=json.loads((root/prev['candidate_paths'][0]/'ground-truth.json').read_text())
    if before['scenario']['variant']!='memory':return False,'previous fault is not memory'
    target=before['resolved']['source_service']
    start=dt.datetime.fromisoformat(before['injection_requested_at'])
    end=dt.datetime.fromisoformat(before['cleanup_completed_at'])+dt.timedelta(seconds=60)
    if chaos:return False,'chaos objects remain'
    seen=False
    for pod in pods['items']:
        labels=pod['metadata'].get('labels',{})
        created=dt.datetime.fromisoformat(pod['metadata']['creationTimestamp'].replace('Z','+00:00'))
        if created>start:return False,'a Pod was replaced: '+pod['metadata']['name']
        statuses=pod['status'].get('containerStatuses',[])
        if not all(c.get('ready') for c in statuses):return False,'Pod not Ready: '+pod['metadata']['name']
        for c in statuses:
            term=c.get('lastState',{}).get('terminated') or {}
            if not term.get('finishedAt'):continue
            finished=dt.datetime.fromisoformat(term['finishedAt'].replace('Z','+00:00'))
            if finished<start:continue
            if labels.get('name')!=target or term.get('reason')!='OOMKilled' or finished>end:
                return False,f'unexpected restart {pod["metadata"]["name"]} {term.get("reason")} {term["finishedAt"]}'
            seen=True
    return (True,f'{target} OOMKilled by its own memory fault {before["scenario"]["scenario_id"]}') if seen else (False,'no matching OOM restart found')


def main():
    parser=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--journal-dir',type=Path,required=True);parser.add_argument('--release',type=Path,required=True)
    parser.add_argument('--max-resumes',type=int,default=6);parser.add_argument('--interval',type=float,default=30)
    args=parser.parse_args();journal_path=args.journal_dir/'journal.json';log=args.journal_dir/'auto-resume.json'
    history=json.loads(log.read_text()) if log.exists() else []
    resumes=0;handled=None
    while True:
        journal=json.loads(journal_path.read_text())
        key=(journal.get('status'),len(journal['attempts']),len(journal.get('soaks',[])))
        if journal.get('status') in ('running',) or key==handled:time.sleep(args.interval);continue
        if journal.get('status')!='stopped_requires_review':print('Collection ended: '+journal.get('status',''),flush=True);return 0
        pods=kubectl_json('-n','sock-shop','get','pods')
        chaos=[i for kind in ('stresschaos','networkchaos','podchaos') for i in kubectl_json('get',kind,'-A')['items']]
        ok,detail=benign(journal,pods=pods,chaos=chaos)
        entry={'at':dt.datetime.now(dt.timezone.utc).isoformat(),'attempts':len(journal['attempts']),'benign':ok,'detail':detail}
        history.append(entry);log.write_text(json.dumps(history,ensure_ascii=False,indent=2)+'\n');handled=key
        print(json.dumps(entry,ensure_ascii=False),flush=True)
        if not ok or resumes>=args.max_resumes:print('Stopping: human review required.',flush=True);return 1
        resumes+=1
        subprocess.call(['caffeinate','-dims',sys.executable,str(ROOT/'scripts/run_dataset_collection.py'),'--release',str(args.release),
                         '--execute','--max-cases','200','--resume',str(args.journal_dir)],cwd=ROOT)


if __name__=='__main__':raise SystemExit(main())
