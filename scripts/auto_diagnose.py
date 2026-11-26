#!/usr/bin/env python3
"""Alert → incident report automatically, with live Time-to-Diagnosis (proposal §4 step 9, §6.2 TTD).

Polls the collector, and for each NEW captured incident builds context and calls Gemini (B3 by default).
Spend is explicit and bounded:
  * --max-calls is required (each incident = 1 generation + 1 query embedding, more with --with-cases);
  * incidents that existed before the worker started are ignored;
  * it pauses while the dataset collection controller runs, so scenario alerts are never diagnosed live
    (benchmark diagnoses use the precommitted offline window instead).
Live TTD here is for the demo/product path; it is reported separately from replay latency.
"""
import argparse
import datetime as dt
import fcntl
import json
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
COLLECTOR='http://127.0.0.1:8000'
OUT=ROOT/'results/live-diagnoses'


def utc(value):return dt.datetime.fromisoformat(value)
def now():return dt.datetime.now(dt.timezone.utc)


def collection_active(lock_path=ROOT/'.runtime/collection-controller.lock'):
    with open(lock_path,'a+') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return True
        fcntl.flock(lock,fcntl.LOCK_UN);return False


def fetch(path):
    with urllib.request.urlopen(COLLECTOR+path,timeout=15) as response:return json.load(response)


READ_ALERT=('import json,sqlite3,sys;c=sqlite3.connect("file:/data/incidents.sqlite?mode=ro",uri=True);'
            'r=c.execute("SELECT alert FROM incidents WHERE id=?",(sys.argv[1],)).fetchone();print(r[0] if r else "null")')


def alert_labels(incident_id):
    """Read the alert stored by the collector (read-only); the HTTP API does not expose labels."""
    out=subprocess.run(['kubectl','--kubeconfig',str(ROOT/'.runtime/kubeconfig'),'-n','monitoring','exec','deploy/incident-collector',
                        '--','python','-c',READ_ALERT,incident_id],capture_output=True,text=True,timeout=30,check=True).stdout
    return (json.loads(out) or {}).get('labels',{})


def matches(labels,rules):
    return all(re.fullmatch(pattern,str(labels.get(key,''))) for key,pattern in rules)


def new_incidents(listing,started_at,done):
    return sorted((i for i in listing if i['status'] in ('captured','partial') and i['id'] not in done
                   and utc(i['received_at'])>=started_at),key=lambda i:i['received_at'])


def ttd_record(incident,manifest,context_ready,report_at,result,mode,error=None):
    received=utc(incident['received_at'])
    seconds=lambda a,b:(b-a).total_seconds() if a and b else None
    capture_ready=utc(manifest['context_ready_at']) if manifest.get('context_ready_at') else None
    return {'incident_id':incident['id'],'mode':mode,'alert_received_at':incident['received_at'],
            'capture_ready_at':capture_ready.isoformat() if capture_ready else None,
            'context_built_at':context_ready.isoformat() if context_ready else None,
            'report_at':report_at.isoformat() if report_at else None,
            'ttd_seconds':seconds(received,report_at),
            'components_seconds':{'alert_to_capture':seconds(received,capture_ready),'capture_to_context':seconds(capture_ready,context_ready),
                                  'llm_and_retrieval':result.get('analysis_latency_seconds') if result else None},
            'context_id':result.get('context_id') if result else None,
            'status':'report_generated' if result and not error else 'failed','error':error,
            'note':'Live alert-to-report time including the collector post-alert wait; not replay latency.'}


def process(incident,mode,with_cases):
    from app.live_context import prepare_live
    detail=fetch('/incidents/'+incident['id']);manifest=detail.get('manifest') or {}
    result=None;context_ready=None;error=None
    try:
        context,_,_=prepare_live(incident['id']);context_ready=now()
        if with_cases:
            from app.diagnosis_cases import diagnose_with_cases
            result=diagnose_with_cases(context,mode)
        else:
            from app.diagnosis import diagnose
            result=diagnose(context,mode)
    except Exception as exc:error=f'{type(exc).__name__}: {exc}'
    record=ttd_record(incident,manifest,context_ready,now() if result else None,result,mode,error)
    folder=OUT/incident['id'];folder.mkdir(parents=True,exist_ok=True)
    (folder/'ttd.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
    return record


def main():
    parser=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--max-calls',type=int,required=True,help='Hard cap on diagnosed incidents (API spend)')
    parser.add_argument('--mode',choices=['B2','B3'],default='B3');parser.add_argument('--with-cases',action='store_true')
    parser.add_argument('--interval',type=float,default=5.0)
    parser.add_argument('--match',action='append',default=[],metavar='LABEL=REGEX',
                        help='Only diagnose alerts whose labels fully match, e.g. alertname=SockShopCPUHigh pod=payment-.*')
    args=parser.parse_args()
    if not 1<=args.max_calls<=50:parser.error('Use 1..50 calls per run')
    try:rules=[tuple(item.split('=',1)) for item in args.match];[re.compile(p) for _,p in rules]
    except (ValueError,re.error):parser.error('--match must be LABEL=REGEX')
    started=now();done=set();calls=0
    print(f'Watching {COLLECTOR} for incidents after {started.isoformat()}; cap {args.max_calls} diagnoses',flush=True)
    while calls<args.max_calls:
        if collection_active():
            time.sleep(30);continue
        try:listing=fetch('/incidents')
        except OSError as exc:print('Collector unreachable: '+str(exc),flush=True);time.sleep(args.interval*3);continue
        for incident in new_incidents(listing,started,done):
            if calls>=args.max_calls or collection_active():break
            done.add(incident['id'])
            if rules:
                try:labels=alert_labels(incident['id'])
                except (subprocess.SubprocessError,ValueError) as exc:print('Label lookup failed, skipped: '+str(exc),flush=True);continue
                if not matches(labels,rules):continue
            calls+=1
            record=process(incident,args.mode,args.with_cases)
            print(json.dumps({k:record[k] for k in ('incident_id','status','ttd_seconds','error')}),flush=True)
        time.sleep(args.interval)
    print('Call cap reached; stopping.',flush=True)


if __name__=='__main__':main()
