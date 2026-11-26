#!/usr/bin/env python3
"""Roll out frontend tracing only after pinned-image fixture verification."""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import signal
import subprocess
import sys
import time
import urllib.request
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.experiment_runtime import KUBE,kube_json,experiment_lock,snapshot,health_issues
from app.frontend_tracing_policy import apply_frontend_tracing
from app.context_builder import observed_peer
from scripts.verify_telemetry import get,trace_services
from scripts.deploy_native_go import wait_service_routes


def kube(args,payload=None):
    return subprocess.run(KUBE+['-n','sock-shop']+args,input=json.dumps(payload).encode() if payload else None,
        check=True,capture_output=True,timeout=150)


def main():
    def stop(*_):raise KeyboardInterrupt('Rollback frontend tracing if verification incomplete')
    signal.signal(signal.SIGTERM,stop)
    parser=argparse.ArgumentParser();parser.add_argument('--verification',type=Path,required=True);args=parser.parse_args()
    proof=json.loads(args.verification.read_text());script=(ROOT/'infra/tracing/frontend-tracing.js').read_text()
    if proof.get('status')!='pinned_frontend_node_fixture_verified' or proof['tracer_sha256']!=hashlib.sha256(script.encode()).hexdigest():
        raise ValueError('Matching pinned frontend Node fixture proof required')
    directory=ROOT/'results/frontend-tracing-rollout'/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ');directory.mkdir(parents=True)
    report={'status':'started','database_changed':False,'rollout_requested':False,'verification':str(args.verification)}
    def save():(directory/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    forward=None;log=None;original=None
    with experiment_lock():
        try:
            if health_issues(snapshot()):raise RuntimeError('Testbed unhealthy')
            source=kube_json('sock-shop','get','deployment','front-end');original=source['spec']['template']
            if original['spec']['containers'][0]['image']!=proof['source_image']:raise ValueError('Frontend image changed')
            package=kube(['exec','deployment/front-end','--','node','-e',
                'var p=require("./package.json"); console.log(JSON.stringify({cwd:process.cwd(),node:process.version,scripts:p.scripts}));'])
            info=json.loads(package.stdout.decode().strip().splitlines()[-1]);report['runtime']=info
            if info['cwd']!='/usr/src/app' or info['scripts'].get('start')!='node server.js' or info['scripts'].get('prestart') or info['scripts'].get('poststart'):
                raise ValueError('Frontend startup differs from reviewed package')
            if info['node']!=proof['fixture_result']['node']:raise ValueError('Frontend runtime differs from compatibility proof')
            (directory/'before-template.json').write_text(json.dumps(original,indent=2)+'\n')
            staged=apply_frontend_tracing([source],script);desired=staged[0];desired.pop('status',None)
            metadata=desired['metadata'];desired['metadata']={k:metadata[k] for k in ('name','namespace','labels') if k in metadata}
            annotations={k:v for k,v in metadata.get('annotations',{}).items() if k!='kubectl.kubernetes.io/last-applied-configuration'}
            if annotations:desired['metadata']['annotations']=annotations
            payload={'apiVersion':'v1','kind':'List','items':staged};path=directory/'rollout.json';path.write_text(json.dumps(payload,indent=2)+'\n')
            kube(['apply','--dry-run=server','-f',str(path)])
            report['rollout_requested']=True;save();kube(['apply','-f',str(path)])
            kube(['rollout','status','deployment/front-end','--timeout=120s']);wait_service_routes(directory)
            log=(directory/'smoke-forward.log').open('w')
            forward=subprocess.Popen(KUBE+['-n','sock-shop','port-forward','--address=127.0.0.1','service/front-end','18080:80'],stdout=log,stderr=subprocess.STDOUT)
            deadline=time.monotonic()+30
            while True:
                if forward.poll() is not None:raise RuntimeError('Smoke tunnel exited')
                try:urllib.request.urlopen('http://127.0.0.1:18080/',timeout=3).close();break
                except OSError:
                    if time.monotonic()>deadline:raise RuntimeError('Smoke tunnel not ready')
                    time.sleep(1)
            start=time.time()
            subprocess.run([sys.executable,str(ROOT/'traffic/run.py'),'--url','http://127.0.0.1:18080','--profile','checkout','--journeys','3','--output',str(directory/'checkout.json')],check=True,timeout=180)
            report['smoke_window_start']=start
            confirmed=False;deadline=time.monotonic()+40;attempts=[]
            while time.monotonic()<deadline:
                try:
                    traces=get('http://127.0.0.1:16686/api/v3/traces',{'query.service_name':'front-end','query.num_traces':500,
                        'query.start_time_min':dt.datetime.fromtimestamp(start,dt.timezone.utc).isoformat(),
                        'query.start_time_max':dt.datetime.now(dt.timezone.utc).isoformat()})
                    (directory/'live-traces.json').write_text(json.dumps(traces)+'\n')
                    groups=trace_services(traces);peers=set()
                    for document in traces if isinstance(traces,list) else [traces]:
                        for resource in document.get('result',{}).get('resourceSpans',[]):
                            service=next((a.get('value',{}).get('stringValue') for a in resource.get('resource',{}).get('attributes',[]) if a.get('key')=='service.name'),None)
                            if service!='front-end':continue
                            for scope in resource.get('scopeSpans',[]):
                                for span in scope.get('spans',[]):
                                    if span.get('kind')==3:
                                        peer=observed_peer(span.get('attributes',[]),'client')
                                        if peer:peers.add(peer)
                    report['observed_frontend_client_peers']=sorted(peers)
                    report['cross_service_trace_count']=sum('front-end' in names and len(names)>1 for names in groups.values())
                    attempts.append({'at':dt.datetime.now(dt.timezone.utc).isoformat(),'trace_count':len(groups),'peers':sorted(peers)})
                    if report['cross_service_trace_count'] and {'user','carts','orders','catalogue'}<=peers:
                        confirmed=True;break
                except Exception as exc:attempts.append({'error_type':type(exc).__name__})
                time.sleep(2)
            (directory/'trace-probes.json').write_text(json.dumps(attempts,indent=2)+'\n')
            if not confirmed:raise RuntimeError('Cross-service frontend/peer tracing not verified')
            policy_path=ROOT/'infra/tracing/frontend-policy.json';policy=json.loads(policy_path.read_text());policy.update(enabled=True,status='pinned_node_and_live_cross_service_verified')
            policy_path.write_text(json.dumps(policy,indent=2)+'\n')
            subprocess.run([sys.executable,str(ROOT/'scripts/prepare_sock_shop.py')],check=True)
            report['status']='frontend_tracing_live_verified_requires_collector_update_and_soak'
        except BaseException as exc:
            report.update(status='failed',error_type=type(exc).__name__,error=str(exc))
            if report['rollout_requested'] and original:
                kube(['patch','deployment/front-end','--type=merge','-p',json.dumps({'spec':{'template':original}})])
                kube(['rollout','status','deployment/front-end','--timeout=120s']);report['rollback_completed']=True
            raise
        finally:
            if forward and forward.poll() is None:forward.terminate();forward.wait(timeout=10)
            if log:log.close()
            save();print('Frontend tracing rollout: '+str(directory)+'; '+report['status'],flush=True)


if __name__=='__main__':main()
