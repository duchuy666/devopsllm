#!/usr/bin/env python3
"""Quiesced MongoDB cutover with fresh backups, restore and cache readback."""
import argparse
import datetime as dt
import hashlib
import json
import os
import signal
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.experiment_runtime import KUBE,experiment_lock,kube_json,snapshot,health_issues
from app.db_cache_policy import TARGETS
from scripts.verify_db_backups import inventory,execute
from scripts.deploy_native_go import wait_service_routes

WRITERS=('front-end','user','carts','orders','queue-master')


def main():
    def interrupted(*_):raise KeyboardInterrupt('Interrupted; preserve backups and cutover recovery state')
    signal.signal(signal.SIGTERM,interrupted)
    parser=argparse.ArgumentParser();parser.add_argument('--packet',type=Path,required=True)
    parser.add_argument('--restore-verification',type=Path,required=True);args=parser.parse_args()
    verification=json.loads(args.restore_verification.read_text())
    if verification['status']!='all_three_online_backups_restore_verified':raise ValueError('Successful isolated restore verification required')
    if {r['service'] for r in verification['targets']}!=set(TARGETS):raise ValueError('Restore verification lacks targets')
    packet=args.packet;plan=json.loads((packet/'execution-plan.json').read_text())
    for name,digest in plan['files_sha256'].items():
        if Path(name).name!=name or hashlib.sha256((packet/name).read_bytes()).hexdigest()!=digest:raise ValueError('Rollout packet changed')
    manifest=ROOT/'infra/sock-shop/local-emulated.yaml'
    if hashlib.sha256(manifest.read_bytes()).hexdigest()!=plan['source_manifest_sha256']:raise ValueError('Source manifest changed since preparation')
    directory=ROOT/'results/db-cache-cutover'/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ');directory.mkdir(parents=True)
    report={'status':'started','targets':[],'writers':{},'isolated_restore_verification':str(args.restore_verification),
        'database_rollout_requested':False,'all_data_restored':False,'source_policy_activated':False}
    def save():(directory/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    forward=None;forward_log=None
    with experiment_lock():
        try:
            issues=health_issues(snapshot())
            if issues:raise RuntimeError('Testbed not healthy: '+str(issues))
            for name in WRITERS:
                report['writers'][name]=kube_json('sock-shop','get','deployment',name)['spec'].get('replicas',1)
            for name in TARGETS:
                current=kube_json('sock-shop','get','deployment',name)
                proof=next(r for r in verification['targets'] if r['service']==name)
                if current['spec']['template']['spec']['containers'][0]['image']!=proof['source_image']:raise RuntimeError('Database image differs from isolated restore proof')
                (directory/(name+'-before-deployment.json')).write_text(json.dumps(current,indent=2)+'\n')
            execute(['-n','sock-shop','apply','--dry-run=server','-f',str(packet/'database-only.yaml')])
            save();print('Quiescing five writer deployments',flush=True)
            execute(['-n','sock-shop','scale']+['deployment/'+n for n in WRITERS]+['--replicas=0'])
            deadline=time.monotonic()+120
            while kube_json('sock-shop','get','pods','-l','name in ('+','.join(WRITERS)+')')['items']:
                if time.monotonic()>deadline:raise RuntimeError('Writers did not quiesce')
                time.sleep(2)
            for name in TARGETS:
                source='deployment/'+name;before=inventory(source);archive=directory/(name+'.archive.gz')
                with os.fdopen(os.open(archive,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'wb') as out:
                    subprocess.run(KUBE+['-n','sock-shop','exec',source,'--','timeout','120s','mongodump','--archive','--gzip'],stdout=out,stderr=subprocess.PIPE,check=True,timeout=150)
                if not archive.stat().st_size or inventory(source)!=before:raise RuntimeError('Fresh backup failed consistency check')
                report['targets'].append({'service':name,'archive':archive.name,'archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'before_inventory':before})
                save();print(name+': quiesced backup saved',flush=True)
            report['database_rollout_requested']=True;save()
            execute(['-n','sock-shop','apply','-f',str(packet/'database-only.yaml')])
            for row in report['targets']:
                name=row['service'];source='deployment/'+name
                execute(['-n','sock-shop','rollout','status',source,'--timeout=150s'])
                cache=execute(['-n','sock-shop','exec',source,'--','timeout','10s','mongo','--quiet','--eval','print(db.serverStatus().wiredTiger.cache["maximum bytes configured"]);'])
                row['cache_max_bytes']=int(cache.stdout.decode().strip().splitlines()[-1])
                if row['cache_max_bytes']!=134217728:raise RuntimeError('Startup cache readback mismatch')
                archive=directory/row['archive']
                if hashlib.sha256(archive.read_bytes()).hexdigest()!=row['archive_sha256']:raise RuntimeError('Fresh backup changed')
                restored=execute(['-n','sock-shop','exec','-i',source,'--','timeout','120s','mongorestore','--archive','--gzip','--drop'],input=archive.read_bytes())
                (directory/(name+'-restore.log')).write_bytes(restored.stdout+restored.stderr)
                row['after_inventory']=inventory(source)
                if row['after_inventory']!=row['before_inventory']:raise RuntimeError('Cutover data inventory mismatch')
                row['restore_verified']=True;save();print(name+': restored, inventory/cache verified',flush=True)
            report['all_data_restored']=True;save()
            for name,count in report['writers'].items():execute(['-n','sock-shop','scale','deployment/'+name,'--replicas='+str(count)])
            for name,count in report['writers'].items():
                if count:execute(['-n','sock-shop','rollout','status','deployment/'+name,'--timeout=150s'])
            wait_service_routes(directory)
            forward_log=(directory/'smoke-forward.log').open('w')
            forward=subprocess.Popen(KUBE+['-n','sock-shop','port-forward','--address=127.0.0.1','service/front-end','18080:80'],stdout=forward_log,stderr=subprocess.STDOUT)
            deadline=time.monotonic()+30
            while True:
                if forward.poll() is not None:raise RuntimeError('Dedicated smoke tunnel exited')
                try:urllib.request.urlopen('http://127.0.0.1:18080/',timeout=3).close();break
                except OSError:
                    if time.monotonic()>deadline:raise RuntimeError('Smoke tunnel not ready')
                    time.sleep(1)
            subprocess.run([sys.executable,str(ROOT/'traffic/run.py'),'--url','http://127.0.0.1:18080','--profile','checkout','--journeys','3','--output',str(directory/'checkout.json')],check=True,timeout=180)
            policy_path=ROOT/'infra/sock-shop/db-cache-policy.json';policy=json.loads(policy_path.read_text());policy.update(enabled=True,status='poststart_rollout_and_restore_verified')
            policy_path.write_text(json.dumps(policy,indent=2)+'\n')
            subprocess.run([sys.executable,str(ROOT/'scripts/prepare_sock_shop.py')],check=True)
            report.update(status='cutover_verified_requires_fresh_soak',source_policy_activated=True)
        except BaseException as exc:
            report.update(status='failed_requires_recovery',error_type=type(exc).__name__,error=str(exc))
            # Resume writers only if no DB mutation occurred or all restores passed.
            if not report['database_rollout_requested'] or report['all_data_restored']:
                for name,count in report['writers'].items():
                    try:execute(['-n','sock-shop','scale','deployment/'+name,'--replicas='+str(count)])
                    except Exception:report['writer_resume_unconfirmed']=True
            else:report['writers_kept_quiesced_for_data_recovery']=True
            raise
        finally:
            if forward and forward.poll() is None:forward.terminate();forward.wait(timeout=10)
            if forward_log:forward_log.close()
            save();print('Cutover artifact: '+str(directory)+'; '+report['status'],flush=True)


if __name__=='__main__':main()
