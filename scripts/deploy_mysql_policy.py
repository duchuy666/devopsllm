#!/usr/bin/env python3
"""Quiesced MySQL memory-policy rollout with fresh backup and verified restore."""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import urllib.request
import argparse
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.experiment_runtime import KUBE,experiment_lock,kube_json,snapshot,health_issues
from app.mysql_policy import apply_mysql_policy
from scripts import mysql_runtime as db
from scripts.verify_mysql_policy import kube
from scripts.deploy_native_go import wait_service_routes

WRITERS=('front-end','catalogue')


def private_json(path,value):
    with os.fdopen(os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w') as out:
        json.dump(value,out,indent=2)


def main():
    def stop(*_):raise KeyboardInterrupt('Interrupted; keep MySQL recovery state and backups')
    signal.signal(signal.SIGTERM,stop)
    parser=argparse.ArgumentParser();parser.add_argument('--verification',type=Path,required=True);args=parser.parse_args()
    proof=json.loads(args.verification.read_text());config=(ROOT/'infra/sock-shop/mysql-memory.cnf').read_text()
    if proof.get('status')!='isolated_mysql_restore_and_config_verified' or not proof.get('startup_tcp_readiness_verified'):
        raise ValueError('Successful isolated restore and TCP startup proof required')
    if hashlib.sha256(config.encode()).hexdigest()!=proof['config_sha256']:raise ValueError('Verified config changed')
    directory=ROOT/'results/mysql-cutover'/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ');directory.mkdir(parents=True)
    report={'status':'started','writers':{},'database_rollout_requested':False,'data_restored':False,
        'verification':str(args.verification),'config_sha256':proof['config_sha256'],'source_policy_activated':False}
    def save():(directory/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    forward=None;log=None
    with experiment_lock():
        try:
            if health_issues(snapshot()):raise RuntimeError('Testbed unhealthy')
            source=kube_json('sock-shop','get','deployment','catalogue-db')
            if source['spec']['template']['spec']['containers'][0]['image']!=proof['source_image']:raise ValueError('Database image changed')
            if db.sql(db.SOURCE,'SELECT VERSION();')!=proof['version']:raise ValueError('Database version differs from proof')
            private_json(directory/'before-deployment.json',source)
            for name in WRITERS:report['writers'][name]=kube_json('sock-shop','get','deployment',name)['spec'].get('replicas',1)
            staged=apply_mysql_policy([source],config)
            # Strip server-owned metadata before serializing an apply request.
            desired=staged[0];desired.pop('status',None)
            desired['metadata']={k:desired['metadata'][k] for k in ('name','namespace')}
            desired['spec']['replicas']=source['spec'].get('replicas',1)
            payload={'apiVersion':'v1','kind':'List','items':staged}
            private_json(directory/'rollout.json',payload)
            kube(['apply','--dry-run=server','-f',str(directory/'rollout.json')])
            save();print('Quiescing frontend/catalogue writers',flush=True)
            kube(['scale']+['deployment/'+n for n in WRITERS]+['--replicas=0'])
            deadline=time.monotonic()+120
            while kube_json('sock-shop','get','pods','-l','name in (front-end,catalogue)')['items']:
                if time.monotonic()>deadline:raise RuntimeError('Writers did not quiesce')
                time.sleep(2)
            report['before_inventory']=db.inventory(db.SOURCE)
            report['backup_sha256']=db.backup(directory/'catalogue.sql')
            if db.inventory(db.SOURCE)!=report['before_inventory']:raise RuntimeError('Quiesced source inventory changed')
            save();print('Fresh MySQL backup saved; requesting rollout',flush=True)
            report['database_rollout_requested']=True;save()
            kube(['apply','-f',str(directory/'rollout.json')])
            kube(['rollout','status','deployment/catalogue-db','--timeout=120s'])
            report['after_variables']=db.variables(db.SOURCE)
            if any(report['after_variables'].get(k)!=v for k,v in db.EXPECTED.items()):raise RuntimeError('Startup variables mismatch')
            if hashlib.sha256((directory/'catalogue.sql').read_bytes()).hexdigest()!=report['backup_sha256']:raise RuntimeError('Backup changed')
            restored=db.restore(directory/'catalogue.sql',db.SOURCE)
            (directory/'restore.log').write_bytes(restored.stderr)
            report['after_inventory']=db.inventory(db.SOURCE)
            if report['after_inventory']!=report['before_inventory']:raise RuntimeError('Restored schema/rows/checksums/accounts differ')
            if db.sql(db.SOURCE,'SELECT VERSION();')!=proof['version']:raise RuntimeError('MySQL version changed')
            report['data_restored']=True;save();print('MySQL data and startup variables verified',flush=True)
            for name,count in report['writers'].items():kube(['scale','deployment/'+name,'--replicas='+str(count)])
            for name,count in report['writers'].items():
                if count:kube(['rollout','status','deployment/'+name,'--timeout=120s'])
            wait_service_routes(directory)
            log=(directory/'smoke-forward.log').open('w')
            forward=subprocess.Popen(KUBE+['-n','sock-shop','port-forward','--address=127.0.0.1','service/front-end','18080:80'],stdout=log,stderr=subprocess.STDOUT)
            deadline=time.monotonic()+30
            while True:
                if forward.poll() is not None:raise RuntimeError('Smoke tunnel exited')
                try:urllib.request.urlopen('http://127.0.0.1:18080/',timeout=3).close();break
                except OSError:
                    if time.monotonic()>deadline:raise RuntimeError('Smoke tunnel not ready')
                    time.sleep(1)
            subprocess.run([sys.executable,str(ROOT/'traffic/run.py'),'--url','http://127.0.0.1:18080','--profile','checkout','--journeys','3','--output',str(directory/'checkout.json')],check=True,timeout=180)
            policy_path=ROOT/'infra/sock-shop/mysql-memory-policy.json';policy=json.loads(policy_path.read_text())
            policy.update(enabled=True,status='isolated_restore_cutover_and_startup_verified');policy_path.write_text(json.dumps(policy,indent=2)+'\n')
            subprocess.run([sys.executable,str(ROOT/'scripts/prepare_sock_shop.py')],check=True)
            report.update(status='mysql_cutover_verified_requires_soak',source_policy_activated=True)
        except BaseException as exc:
            report.update(status='failed_requires_recovery',error_type=type(exc).__name__,error=str(exc))
            if not report['database_rollout_requested'] or report['data_restored']:
                for name,count in report['writers'].items():
                    try:kube(['scale','deployment/'+name,'--replicas='+str(count)])
                    except Exception:report['writer_resume_unconfirmed']=True
            else:report['writers_kept_quiesced_for_recovery']=True
            raise
        finally:
            if forward and forward.poll() is None:forward.terminate();forward.wait(timeout=10)
            if log:log.close()
            save();print('MySQL cutover: '+str(directory)+'; '+report['status'],flush=True)


if __name__=='__main__':main()
