#!/usr/bin/env python3
"""Prepare a bounded, reviewable DB rollout packet. Never contacts the cluster."""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import yaml

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.db_cache_policy import TARGETS,NAME


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=ROOT/'results/db-cache-rollout'/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    args=parser.parse_args();directory=args.output
    if directory.exists():parser.error('Refuse to overwrite a rollout packet')
    directory.mkdir(parents=True)
    preview=directory/'full-preview.yaml'
    subprocess.run([sys.executable,str(ROOT/'scripts/prepare_sock_shop.py'),'--db-cache-hook','--output',str(preview)],check=True)
    rows=[r for r in yaml.safe_load_all(preview.read_text()) if r]
    selected=[r for r in rows if (r['kind']=='Deployment' and r['metadata']['name'] in TARGETS) or
              (r['kind']=='ConfigMap' and r['metadata']['name']==NAME)]
    if len(selected)!=4 or any(r['metadata'].get('namespace')!='sock-shop' for r in selected):
        raise ValueError('Unexpected rollout scope')
    apply_file=directory/'database-only.yaml';apply_file.write_text(yaml.safe_dump_all(selected,sort_keys=False))
    manifest=ROOT/'infra/sock-shop/local-emulated.yaml'
    report={'status':'prepared_not_deployed','namespace':'sock-shop','database_targets':list(TARGETS),
        'desired_cache_bytes':134217728,'rollout_manifest':apply_file.name,
        'quiesce_writers':['front-end','user','carts','orders','queue-master'],
        'required_before_apply':['Fresh cluster health and no active experiment/chaos',
            'Read actual replicas/images and record rollback templates',
            'Verify mongo, mongodump, mongorestore and timeout tools in each pinned image',
            'Quiesce writers without changing database contents',
            'Create mode-0600 archive backups and record hashes and logical inventory',
            'Restore backups into isolated disposable databases and compare inventory',
            'Server dry-run of the four-resource rollout manifest'],
        'required_after_apply':['Each postStart hook succeeds and readback is exactly134217728 bytes',
            'Restore pre-rollout data before resuming application traffic',
            'Compare logical inventory and archive/restore results',
            'Resume saved replica counts, wait service convergence, run checkout smoke',
            'Enable persistent source policy only after successful verification',
            'Run a fresh soak; old receipts are invalid after Pod replacement'],
        'failure_policy':'Keep backups. If restoration is incomplete, keep writers quiesced and require recovery; do not claim success or discard backups.',
        'source_manifest_sha256':hashlib.sha256(manifest.read_bytes()).hexdigest(),
        'files_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.iterdir() if p.is_file()},
        'cluster_contacted':False,'data_backed_up':False,'data_restored':False,'policy_activated':False,
        'note':'A prepared manifest is not evidence that legacy-image tools or backup/restore have been verified.'}
    (directory/'execution-plan.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'packet':str(directory),'status':report['status'],'resources':len(selected),'cluster_contacted':False},indent=2))


if __name__=='__main__':main()
