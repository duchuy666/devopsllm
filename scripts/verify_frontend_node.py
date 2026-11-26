#!/usr/bin/env python3
"""Run the tracing functional fixture in an isolated copy of the pinned image."""
import datetime as dt
import hashlib
import json
from pathlib import Path
import signal
import subprocess
import sys
import time
import uuid
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.experiment_runtime import KUBE,kube_json,experiment_lock,health_issues,snapshot


def kube(args,payload=None):
    return subprocess.run(KUBE+['-n','sock-shop']+args,input=json.dumps(payload).encode() if payload else None,
        check=True,capture_output=True,timeout=120)


def main():
    def stop(*_):raise KeyboardInterrupt('Clean isolated Node verification resources')
    signal.signal(signal.SIGTERM,stop)
    directory=ROOT/'results/frontend-node-verification'/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ');directory.mkdir(parents=True)
    token=uuid.uuid4().hex[:10];name='shyn-node-check-'+token;created=[]
    report={'status':'started','application_frontend_restarted':False,'external_endpoint_used':False}
    def save():(directory/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    with experiment_lock():
        try:
            if health_issues(snapshot()):raise RuntimeError('Unhealthy testbed')
            deployment=kube_json('sock-shop','get','deployment','front-end');image=deployment['spec']['template']['spec']['containers'][0]['image']
            script=(ROOT/'infra/tracing/frontend-tracing.js').read_text();fixture=(ROOT/'tests/frontend-tracing-smoke.js').read_text()
            report.update(source_image=image,tracer_sha256=hashlib.sha256(script.encode()).hexdigest(),fixture_sha256=hashlib.sha256(fixture.encode()).hexdigest())
            labels={'thesis.shyn/node-check':token}
            cm={'apiVersion':'v1','kind':'ConfigMap','metadata':{'name':name,'namespace':'sock-shop','labels':labels},
                'data':{'frontend-tracing.js':script,'frontend-tracing-smoke.js':fixture}}
            pod={'apiVersion':'v1','kind':'Pod','metadata':{'name':name,'namespace':'sock-shop','labels':labels},'spec':{
                'restartPolicy':'Never','containers':[{'name':'check','image':image,'imagePullPolicy':'IfNotPresent',
                    'command':['node','/opt/shyn-test/frontend-tracing-smoke.js'],
                    'env':[{'name':'SHYN_TRACER_PATH','value':'/opt/shyn-test/frontend-tracing.js'}],
                    'resources':{'requests':{'cpu':'25m','memory':'64Mi'},'limits':{'cpu':'500m','memory':'384Mi'}},
                    'securityContext':{'runAsUser':10001,'runAsNonRoot':True,'readOnlyRootFilesystem':True},
                    'volumeMounts':[{'name':'source','mountPath':'/opt/shyn-test','readOnly':True}]}],
                'volumes':[{'name':'source','configMap':{'name':name,'defaultMode':292}}]}}
            for kind,payload in [('configmap',cm),('pod',pod)]:created.append(kind);kube(['create','-f','-'],payload)
            deadline=time.monotonic()+90
            while True:
                state=kube_json('sock-shop','get','pod',name);phase=state['status']['phase']
                if phase in ('Succeeded','Failed'):break
                if time.monotonic()>deadline:raise RuntimeError('Legacy Node fixture timed out')
                time.sleep(2)
            logs=kube(['logs',name]).stdout.decode();(directory/'fixture.log').write_text(logs)
            if phase!='Succeeded':raise RuntimeError('Legacy Node fixture failed; inspect fixture.log')
            result=json.loads(logs.strip().splitlines()[-1])
            if result.get('status')!='passed' or result.get('exported_spans')!=8:raise RuntimeError('Unexpected fixture result')
            report.update(status='pinned_frontend_node_fixture_verified',fixture_result=result)
        except BaseException as exc:report.update(status='failed_requires_review',error_type=type(exc).__name__,error=str(exc));raise
        finally:
            for kind in reversed(created):
                raw=kube(['get',kind,name,'--ignore-not-found','-o','json']).stdout.decode().strip();owned=json.loads(raw) if raw else {}
                if owned:
                    if owned.get('metadata',{}).get('labels',{}).get('thesis.shyn/node-check')!=token:raise RuntimeError('Cleanup ownership mismatch')
                    kube(['delete',kind,name,'--wait=true','--timeout=60s'])
            report['temporary_cleanup_completed']=True;save();print('Legacy Node verification: '+str(directory)+'; '+report['status'],flush=True)


if __name__=='__main__':main()
