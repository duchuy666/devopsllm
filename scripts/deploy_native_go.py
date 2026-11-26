#!/usr/bin/env python3
"""Development migration of three local images, retaining a manifest rollback."""
import datetime as dt
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.experiment_runtime import KUBE,experiment_lock,kube_json


def run(*args,timeout=300):subprocess.run(list(args),check=True,cwd=ROOT,timeout=timeout)


def wait_service_routes(directory):
    # Deployment Available can precede kube-proxy/EndpointSlice convergence.
    # Probe the same service routes used by the existing frontend, before smoke.
    script="""var http=require('http'),left=3,ok=true;
    ['payment','catalogue','user'].forEach(function(host){var ended=false;
      function done(good){if(ended)return;ended=true;ok=ok&&good;if(--left===0)process.exit(ok?0:1);}
      var req=http.get('http://'+host+'/health',function(r){r.resume();
        console.log(host+':'+r.statusCode);r.on('end',function(){done(r.statusCode===200);});});
      req.setTimeout(5000,function(){req.destroy();done(false);});
      req.on('error',function(e){console.log(host+':'+e.code);done(false);});});"""
    deadline=time.monotonic()+60;attempts=[]
    while time.monotonic()<deadline:
        probe=subprocess.run(KUBE+['-n','sock-shop','exec','deployment/front-end','--','node','-e',script],
            text=True,capture_output=True,timeout=15)
        attempts.append({'at':dt.datetime.now(dt.timezone.utc).isoformat(),'returncode':probe.returncode,
                         'output':probe.stdout[-2000:],'error':probe.stderr[-1000:]})
        (directory/'service-route-probes.json').write_text(json.dumps(attempts,indent=2)+'\n')
        if probe.returncode==0:return
        time.sleep(3)
    raise RuntimeError('Frontend-to-service health routes did not converge')


def main():
    with experiment_lock():
        if kube_json('sock-shop','get','stresschaos,networkchaos,podchaos')['items']:
            raise RuntimeError('Cannot migrate during an active fault')
        directory=ROOT/'results/native-migration'/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        directory.mkdir(parents=True)
        active=ROOT/'infra/native/active-images.json'
        manifest=ROOT/'infra/sock-shop/local-emulated.yaml'
        lock=ROOT/'infra/sock-shop/images.lock.json'
        originals={path:path.read_bytes() if path.exists() else None for path in (active,manifest,lock)}
        (directory/'rollback.yaml').write_bytes(originals[manifest])
        (directory/'deployments-before.json').write_text(json.dumps(kube_json('sock-shop','get','deployments'))+'\n')
        images={}
        for service in ('payment','catalogue','user'):
            build=ROOT/'.runtime/native-builds'/service
            metadata=json.loads((build/'image.json').read_text())
            if hashlib.sha256((build/'app').read_bytes()).hexdigest()!=metadata['binary_sha256']:
                raise ValueError('Native binary changed')
            actual=json.loads(subprocess.check_output(['docker','image','inspect',metadata['tag']],text=True))[0]
            if actual['Id']!=metadata['image_id'] or actual['Architecture']!='arm64':raise ValueError('Local image changed')
            run('minikube','-p','shyn-thesis','image','load',metadata['tag'])
            images[service]=metadata
        changed=False
        result={'status':'preparing','images':images,'gemini_called':False,'published':False}
        try:
            active.write_text(json.dumps({'enabled':True,'status':'experimental_native_go','services':images},indent=2)+'\n')
            changed=True
            run(str(ROOT/'.venv/bin/python'),str(ROOT/'scripts/prepare_sock_shop.py'))
            run(*KUBE,'apply','--dry-run=server','-f',str(manifest))
            run(*KUBE,'apply','-f',str(manifest))
            for service in images:
                run(*KUBE,'-n','sock-shop','rollout','status','deployment/'+service,'--timeout=180s')
            wait_service_routes(directory)
            run(str(ROOT/'.venv/bin/python'),str(ROOT/'traffic/run.py'),'--profile','checkout','--journeys','2',
                '--output',str(directory/'checkout-smoke.json'),timeout=120)
            smoke=json.loads((directory/'checkout-smoke.json').read_text())
            # The traffic CLI also exits nonzero for failures; retain raw output.
            result.update(status='rollout_and_checkout_passed',manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest())
            (directory/'pods-after.json').write_text(json.dumps(kube_json('sock-shop','get','pods'))+'\n')
        except BaseException as exc:
            result.update(status='failed',error_type=type(exc).__name__,error=str(exc))
            for service in images:
                try:
                    logs=subprocess.run(KUBE+['-n','sock-shop','logs','deployment/'+service,'--tail=100'],
                        capture_output=True,text=True,timeout=20)
                    (directory/(service+'-failure.log')).write_text(logs.stdout+logs.stderr)
                except Exception:pass
            if changed:
                for path,contents in originals.items():
                    if contents is None:path.unlink(missing_ok=True)
                    else:path.write_bytes(contents)
                try:
                    run(*KUBE,'apply','-f',str(manifest))
                    for service in images:run(*KUBE,'-n','sock-shop','rollout','status','deployment/'+service,'--timeout=180s')
                    result['rollback_status']='completed'
                except Exception as rollback:result['rollback_error']=str(rollback)
            raise
        finally:
            (directory/'result.json').write_text(json.dumps(result,indent=2)+'\n')
            print(json.dumps({'directory':str(directory),'status':result['status']},indent=2),flush=True)
    return 0


if __name__=='__main__':raise SystemExit(main())
