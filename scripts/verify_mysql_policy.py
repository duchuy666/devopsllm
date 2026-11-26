#!/usr/bin/env python3
"""Verify backup restore and memory config in an isolated pinned MySQL Pod."""
import copy
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
from app.experiment_runtime import KUBE,experiment_lock,kube_json,snapshot,health_issues
from app.mysql_policy import apply_mysql_policy,NAME
from scripts import mysql_runtime as db


def kube(args,payload=None):
    return subprocess.run(KUBE+['-n','sock-shop']+args,input=json.dumps(payload).encode() if payload else None,
        capture_output=True,check=True,timeout=150)


def main():
    def stop(*_):raise KeyboardInterrupt('Preserve backup and clean isolated MySQL resources')
    signal.signal(signal.SIGTERM,stop)
    directory=ROOT/'results/mysql-verification'/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ');directory.mkdir(parents=True)
    token=uuid.uuid4().hex[:10];name='shyn-mysql-check-'+token;created=[]
    report={'status':'started','production_database_restarted':False,'temporary_name':name}
    def save():(directory/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    save()
    with experiment_lock():
        try:
            if health_issues(snapshot()):raise RuntimeError('Unhealthy testbed')
            source=kube_json('sock-shop','get','deployment','catalogue-db');config=(ROOT/'infra/sock-shop/mysql-memory.cnf').read_text()
            report.update(source_image=source['spec']['template']['spec']['containers'][0]['image'],
                config_sha256=hashlib.sha256(config.encode()).hexdigest(),version=db.sql(db.SOURCE,'SELECT VERSION();'),
                before_variables=db.variables(db.SOURCE),source_inventory=db.inventory(db.SOURCE))
            report['archive_sha256']=db.backup(directory/'catalogue.sql')
            if db.inventory(db.SOURCE)!=report['source_inventory']:raise RuntimeError('Source inventory changed during backup')
            staged=apply_mysql_policy([source],config);deployment=staged[0];cm=staged[1]
            cm['metadata']['name']=name;cm['metadata']['labels']={'thesis.shyn/mysql-check':token}
            container=copy.deepcopy(deployment['spec']['template']['spec']['containers'][0])
            container['name']='mysql-check';container.pop('livenessProbe',None)
            container['resources']={'requests':{'cpu':'25m','memory':'64Mi'},'limits':{'cpu':'1000m','memory':'512Mi'}}
            container['volumeMounts']=[v for v in container.get('volumeMounts',[]) if v['name']==NAME]+[{'name':'scratch','mountPath':'/var/lib/mysql'}]
            pod={'apiVersion':'v1','kind':'Pod','metadata':{'name':name,'namespace':'sock-shop',
                'labels':{'thesis.shyn/mysql-check':token}},'spec':{'restartPolicy':'Never','containers':[container],
                'volumes':[{'name':NAME,'configMap':{'name':name,'defaultMode':292}},
                           {'name':'scratch','emptyDir':{'sizeLimit':'512Mi'}}]}}
            for kind,payload in [('configmap',cm),('pod',pod)]:
                created.append(kind);kube(['create','-f','-'],payload)
            kube(['wait','--for=condition=Ready','pod/'+name,'--timeout=120s'])
            report['startup_tcp_readiness_verified']=True
            ready=False
            for _ in range(30):
                try:
                    db.sql(name,'SELECT 1;');ready=True;break
                except (subprocess.SubprocessError,OSError):time.sleep(2)
            if not ready:raise RuntimeError('Isolated MySQL not ready')
            report['isolated_variables']=db.variables(name)
            if any(report['isolated_variables'].get(k)!=v for k,v in db.EXPECTED.items()):raise RuntimeError('Memory configuration readback mismatch')
            restored=db.restore(directory/'catalogue.sql',name)
            (directory/'restore.log').write_bytes(restored.stderr)
            report['restored_inventory']=db.inventory(name)
            if report['restored_inventory']!=report['source_inventory']:raise RuntimeError('Restore schema/row/checksum/account mismatch')
            if db.sql(name,'SELECT VERSION();')!=report['version']:raise RuntimeError('MySQL version changed')
            report['status']='isolated_mysql_restore_and_config_verified'
        except BaseException as exc:
            report.update(status='failed_requires_review',error_type=type(exc).__name__,error=str(exc));raise
        finally:
            for kind in reversed(created):
                raw=kube(['get',kind,name,'--ignore-not-found','-o','json']).stdout.decode().strip()
                owned=json.loads(raw) if raw else {}
                if owned:
                    if owned.get('metadata',{}).get('labels',{}).get('thesis.shyn/mysql-check')!=token:raise RuntimeError('Cleanup ownership mismatch')
                    kube(['delete',kind,name,'--wait=true','--timeout=60s'])
            report['temporary_cleanup_completed']=True;save();print('MySQL verification: '+str(directory)+'; '+report['status'],flush=True)


if __name__=='__main__':main()
