#!/usr/bin/env python3
"""Online backup and isolated restore verification; never roll production DBs."""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.experiment_runtime import KUBE,experiment_lock,kube_json,snapshot,health_issues
from app.db_cache_policy import TARGETS

INVENTORY='''var out=[]; db.getMongo().getDBNames().sort().forEach(function(n){
 if (["admin","local","config"].indexOf(n)>=0) return;
 var d=db.getSiblingDB(n); d.getCollectionNames().sort().forEach(function(c){
 out.push({db:n,collection:c,documents:d.getCollection(c).count(),indexes:d.getCollection(c).getIndexes().length});});});
 print(JSON.stringify(out));'''


def execute(args,**kwargs):
    return subprocess.run(KUBE+args,check=True,capture_output=True,timeout=180,**kwargs)


def inventory(resource):
    result=execute(['-n','sock-shop','exec',resource,'--','timeout','15s','mongo','--quiet','--eval',INVENTORY])
    return json.loads(result.stdout.decode().strip().splitlines()[-1])


def main():
    directory=ROOT/'results/db-backup-verification'/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    directory.mkdir(parents=True);report={'status':'running','targets':[],
        'production_databases_restarted':False,'cutover_backup':False,
        'note':'Online restore validation only. Fresh backups with quiesced writers remain required before a real cutover.'}
    def save():(directory/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    save()
    with experiment_lock():
        issues=health_issues(snapshot())
        if issues:raise RuntimeError('Unhealthy testbed: '+str(issues))
        try:
            for service in TARGETS:
                token=uuid.uuid4().hex[:10];name='shyn-restore-'+service+'-'+token
                item={'service':service,'status':'started','temporary_pod':name};report['targets'].append(item);save()
                archive=directory/(service+'.archive.gz');created=False
                try:
                    source='deployment/'+service;before=inventory(source);item['source_inventory_before']=before
                    deployment=kube_json('sock-shop','get','deployment',service)
                    image=deployment['spec']['template']['spec']['containers'][0]['image'];item['source_image']=image
                    descriptor=os.open(archive,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
                    with os.fdopen(descriptor,'wb') as handle:
                        backup=subprocess.run(KUBE+['-n','sock-shop','exec',source,'--','timeout','120s','mongodump','--archive','--gzip'],
                            stdout=handle,stderr=subprocess.PIPE,timeout=150,check=True)
                    after=inventory(source);item['source_inventory_after']=after
                    if before!=after:raise RuntimeError('Source inventory changed during online snapshot; do not accept backup')
                    if not archive.stat().st_size:raise RuntimeError('Empty backup archive')
                    item['archive_bytes']=archive.stat().st_size;item['archive_sha256']=hashlib.sha256(archive.read_bytes()).hexdigest()
                    pod={'apiVersion':'v1','kind':'Pod','metadata':{'name':name,'namespace':'sock-shop',
                        'labels':{'thesis.shyn/restore-check':token}},'spec':{'restartPolicy':'Never',
                        'containers':[{'name':'restore','image':image,'imagePullPolicy':'IfNotPresent',
                            'command':['sh','-ec','mkdir -p /tmp/shyn-restore; exec mongod --dbpath /tmp/shyn-restore --bind_ip 127.0.0.1 --port 27017'],
                            'resources':{'requests':{'cpu':'25m','memory':'64Mi'},'limits':{'cpu':'500m','memory':'512Mi'}},
                            'volumeMounts':[{'name':'scratch','mountPath':'/tmp'}]}],
                        'volumes':[{'name':'scratch','emptyDir':{'sizeLimit':'256Mi'}}]}}
                    created=True
                    execute(['create','-f','-'],input=json.dumps(pod).encode())
                    execute(['-n','sock-shop','wait','--for=condition=Ready','pod/'+name,'--timeout=90s'])
                    expression='var r=db.adminCommand({setParameter:1,wiredTigerEngineRuntimeConfig:"cache_size=128M"}); if(r.ok!==1)quit(2);'
                    for attempt in range(10):
                        ready=subprocess.run(KUBE+['-n','sock-shop','exec',name,'--','timeout','5s','mongo','--quiet','--eval',expression],capture_output=True,timeout=15)
                        if ready.returncode==0:break
                        time.sleep(2)
                    else:raise RuntimeError('Isolated database did not become reachable')
                    restored=execute(['-n','sock-shop','exec','-i',name,'--','timeout','120s','mongorestore','--archive','--gzip','--drop'],input=archive.read_bytes())
                    (directory/(service+'-restore.log')).write_bytes(restored.stdout+restored.stderr)
                    observed=inventory(name);item['restored_inventory']=observed
                    if before!=observed:raise RuntimeError('Restored collection/document/index counts differ')
                    item['status']='archive_restored_inventory_matches'
                finally:
                    if created:
                        raw=execute(['-n','sock-shop','get','pod',name,'--ignore-not-found','-o','json']).stdout.decode().strip()
                        owned=json.loads(raw) if raw else {}
                        if owned and owned.get('metadata',{}).get('labels',{}).get('thesis.shyn/restore-check')!=token:
                            raise RuntimeError('Cleanup ownership mismatch')
                        if owned:execute(['-n','sock-shop','delete','pod',name,'--wait=true','--timeout=60s'])
                        item['temporary_pod_cleanup_completed']=True
                    save()
                print(service+': isolated restore verified; original DB not restarted',flush=True)
            report['status']='all_three_online_backups_restore_verified'
        except BaseException as exc:
            report.update(status='failed_requires_review',error_type=type(exc).__name__,error=str(exc));raise
        finally:
            save();print('Backup verification artifact: '+str(directory),flush=True)


if __name__=='__main__':main()
