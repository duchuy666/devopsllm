#!/usr/bin/env python3
"""Bounded segmented stability check; each child retains the normal lock/gates."""
import argparse
import datetime as dt
import json
from pathlib import Path
import signal
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--rounds',type=int,default=3);args=parser.parse_args()
    if not 1<=args.rounds<=6:parser.error('Use 1..6 segments of600 seconds')
    directory=ROOT/'results/stability-series'/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ');directory.mkdir(parents=True)
    report={'status':'running','requested_segments':args.rounds,'segment_seconds':600,'segments':[],
        'inter_segment_sample_gaps_seconds':[],'gemini_called':False,
        'note':'Segmented traffic/health observations; not an uninterrupted measurement or proof of long-term absence of OOM.'}
    child=None
    def save():(directory/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    def stop(*_):
        if child and child.poll() is None:child.send_signal(signal.SIGINT)
        raise KeyboardInterrupt('Interrupted segmented soak')
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    save();anchor=None;previous=None
    try:
        for index in range(args.rounds):
            existing=set((ROOT/'results/stability').glob('*/result.json'))
            print(f'Stability segment {index+1}/{args.rounds}',flush=True)
            child=subprocess.Popen([sys.executable,str(ROOT/'scripts/check_stability.py'),'--seconds','600'],cwd=ROOT)
            code=child.wait();created=set((ROOT/'results/stability').glob('*/result.json'))-existing
            if len(created)!=1:raise RuntimeError('Cannot uniquely identify child soak result')
            path=created.pop();result=json.loads(path.read_text());samples=json.loads((path.parent/'samples.json').read_text())
            report['segments'].append({'path':str(path.relative_to(ROOT)),'returncode':code,'status':result['status']});save()
            if code or result['status']!='passed_short_soak':raise RuntimeError('Segment failed; no automatic retry')
            signature=lambda s:(s['pods'],s['support_pods'],s['node_cgroup']['memory_max_bytes'])
            if anchor is None:anchor=(signature(samples[0]),result['manifest_sha256'])
            if result['manifest_sha256']!=anchor[1] or any(signature(s)!=anchor[0] for s in samples):
                raise RuntimeError('Lifecycle/cap/manifest changed within or between segments')
            if previous:
                gap=(dt.datetime.fromisoformat(samples[0]['at'])-dt.datetime.fromisoformat(previous['at'])).total_seconds()
                report['inter_segment_sample_gaps_seconds'].append(gap)
            previous=samples[-1];save()
        report['status']='all_segments_passed';report['passed_traffic_seconds']=600*len(report['segments']);save()
    except BaseException as exc:
        if child and child.poll() is None:
            child.send_signal(signal.SIGINT);child.wait(timeout=30)
        report.update(status='stopped_requires_review',error_type=type(exc).__name__,error=str(exc));save();raise
    finally:print('Stability series artifact: '+str(directory),flush=True)


if __name__=='__main__':main()
