#!/usr/bin/env python3
"""Prepare all planned manifests or execute one reference development candidate.

Never calls Gemini, indexes data, or admits official cases.
"""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import signal
import re
import subprocess
import shutil
import sys
import time
import uuid
import yaml

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.experiment_runtime import KUBE,experiment_lock,snapshot,health_issues,kube_json
from app.stability_timing import audit_timing,VERSION as TIMING_VERSION
from app.collection_release import verify_release
from app.observation_window import crop
from experiments.audit_plan import audit
from experiments.scenario import render
from scripts.capture_window import capture
from scripts.capture_qdisc import capture_qdisc
from scripts.verify_telemetry import get


def now():return dt.datetime.now(dt.timezone.utc).isoformat()


def write(path,value):
    temp=path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    temp.replace(path)


def kube(*args):
    result=subprocess.run(KUBE+['-n','sock-shop']+list(args),capture_output=True,text=True,timeout=30)
    if result.returncode:raise RuntimeError(result.stderr[-3000:])
    return result.stdout


def inventory():
    deployments=kube_json('sock-shop','get','deployments')
    services=kube_json('sock-shop','get','services')
    return ({d['metadata']['name']:d for d in deployments['items']},
            {s['metadata']['name']:s for s in services['items']})


def validate_receipt(path,state,manifest_hash,minimum_seconds=600):
    result=json.loads(path.read_text())
    samples=json.loads((path.parent/'samples.json').read_text())
    if result.get('status')!='passed_short_soak' or result.get('requested_seconds',0)<minimum_seconds:
        raise ValueError('A passing soak of at least 600 seconds is required')
    if result.get('health_gate_version')!='cgroup-working-set-v1':raise ValueError('Soak used an older health gate')
    if result.get('manifest_sha256')!=manifest_hash:raise ValueError('Soak used a different manifest')
    age=(dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(samples[-1]['at'])).total_seconds()
    if not 0<=age<=900:raise ValueError('Soak receipt must end within the last 15 minutes')
    before=samples[-1]
    if before['node_cgroup'].get('events_source')!='memory.events.local':
        raise ValueError('Soak must record local node OOM counters, not hierarchical counters')
    if before['node_cgroup']['memory_max_bytes']!=state['node_cgroup']['memory_max_bytes']:
        raise ValueError('Node memory budget changed after soak')
    if result.get('temporal_gate_version')!=TIMING_VERSION:
        raise ValueError('Soak receipt lacks UTC sampling continuity gate')
    if audit_timing(samples,result.get('elapsed_seconds',0),result.get('sampling_interval_seconds',30))['status']!='passed':
        raise ValueError('Soak receipt has UTC sampling discontinuity')
    for field in ('pods','support_pods'):
        current={p['metadata']['name']:{'uid':p['metadata']['uid'],
            'restarts':{c['name']:c['restartCount'] for c in p['status'].get('containerStatuses',[])}}
            for p in state[field]}
        previous={key.split('/')[-1]:{'uid':p['uid'],'restarts':p['restarts']} for key,p in before[field].items()}
        if current!=previous:raise ValueError('Pod identity/restarts changed since soak')


def lifecycle(state):
    return {p['metadata']['namespace']+'/'+p['metadata']['name']:(p['metadata']['uid'],
        tuple((c['name'],c['restartCount']) for c in p['status'].get('containerStatuses',[])))
        for p in state['pods']+state['support_pods']}


def save_recipe(directory,plan_path=None,receipt=None):
    paths=['scripts/run_scenario.py','experiments/scenario.py','app/experiment_runtime.py',
        'scripts/capture_window.py','scripts/capture_qdisc.py','app/telemetry.py','app/metric_queries.py',
        'app/context_builder.py','app/report_schema.py','app/gemini_provider.py','app/baseline.py',
        'app/collection_release.py','app/observation_window.py','config/collection-protocol.yaml',
        'scripts/run_dataset_collection.py',
        'traffic/steady.py','traffic/run.py','config/testbed.env','config/experiment-protocol.yaml',
        'infra/observability/prometheus-values.yaml','app/db_cache_policy.py',
        'infra/sock-shop/db-cache-policy.json','infra/sock-shop/db-cache-init.sh',
        'scripts/configure_db_cache.py','scripts/prepare_sock_shop.py',
        'app/stability_timing.py','app/mysql_policy.py','app/frontend_tracing_policy.py',
        'infra/sock-shop/mysql-memory-policy.json','infra/sock-shop/mysql-memory.cnf',
        'infra/tracing/frontend-policy.json','infra/tracing/frontend-tracing.js',
        'infra/sock-shop/local-emulated.yaml','infra/native/active-images.json','infra/native/sources.lock.json',
        'infra/native/toolchain.lock.json','infra/native/user-href-compat.patch','requirements-assistant.lock']
    files={};missing=[]
    for name in paths:
        source=ROOT/name
        if not source.exists():missing.append(name);continue
        destination=directory/'provenance/files'/name;destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,destination);files[name]=hashlib.sha256(source.read_bytes()).hexdigest()
    if plan_path and Path(plan_path).exists():
        destination=directory/'provenance/scenario-plan.json';destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(plan_path,destination);files['scenario-plan.json']=hashlib.sha256(destination.read_bytes()).hexdigest()
    if receipt and Path(receipt).exists():
        destination=directory/'provenance/baseline';destination.mkdir(parents=True,exist_ok=True)
        for name in ('result.json','samples.json','traffic.json'):
            source=Path(receipt).parent/name
            if source.exists():
                shutil.copyfile(source,destination/name);files['baseline/'+name]=hashlib.sha256(source.read_bytes()).hexdigest()
    write(directory/'provenance.json',{'captured_at':now(),'files_sha256':files,'missing_files':missing,
        'note':'Fixed allowlist; no .env, credentials or arbitrary workspace files copied.'})


def prepare_all(plan,plan_hash,args):
    deployments,services=inventory()
    directory=ROOT/'.runtime/scenario-manifests'/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    directory.mkdir(parents=True)
    write(directory/'deployments.json',deployments);write(directory/'services.json',services)
    rows=[];validated=set()
    for row in plan['scenarios']:
        manifest,details=render(row,deployments,services,'prepared-'+row['scenario_id'].lower())
        path=directory/(row['scenario_id']+'.yaml')
        path.write_text(yaml.safe_dump(manifest,sort_keys=False))
        entry={'scenario_id':row['scenario_id'],'variant':row['variant'],'split':row['split'],
            'manifest':path.name,'manifest_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'resolved':details}
        if args.server_dry_run_all or (args.server_dry_run and row['variant'] not in validated):
            try:
                kube('create','--dry-run=server','-f',str(path))
                entry['server_dry_run']='passed'
            except Exception as exc:
                entry.update(server_dry_run='failed',error=str(exc))
            validated.add(row['variant'])
        rows.append(entry)
    report={'status':'prepared_only_not_injected','prepared_at':now(),'plan_sha256':plan_hash,
            'count':len(rows),'official_admitted':0,'rows':rows,
            'note':'Service IPs and memory limits are snapshots; execution re-resolves them. Do not bulk-apply these manifests.'}
    write(directory/'manifest-index.json',report)
    print(json.dumps({'directory':str(directory),'prepared':len(rows),'injected':0,
        'server_dry_runs':[(r['variant'],r['server_dry_run']) for r in rows if 'server_dry_run' in r]},indent=2),flush=True)
    return int(any(r.get('server_dry_run')=='failed' for r in rows))


def execute_one(plan,plan_hash,row,args):
    token=uuid.uuid4().hex[:12]
    case_id='CANDIDATE-'+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%f')+'-'+row['scenario_id']
    directory=ROOT/'data/candidates'/case_id;directory.mkdir(parents=True)
    record={'incident_id':case_id,'dataset_role':'development_candidate','scenario':row,
        'plan_sha256':plan_hash,'started_at':now(),'admission_status':'requires_review',
        'fault_effect_status':'requires_review','execution_status':'preparing','gemini_called':False}
    journal=directory/'ground-truth.json'
    write(journal,record)
    save_recipe(directory,getattr(args,'plan',None),args.stability_result)
    release_path=getattr(args,'collection_release',None)
    release=None
    possible_create=False;resource=None;traffic=None;log=None;start=None
    def checkpoint():write(journal,record)
    try:
        if release_path:
            shutil.copyfile(release_path,directory/'collection-release.json')
            record['collection_release_sha256']=hashlib.sha256(Path(release_path).read_bytes()).hexdigest()
        deployments,services=inventory()
        manifest,details=render(row,deployments,services,'case-'+row['scenario_id'].lower()+'-'+token)
        manifest['metadata']['labels']['thesis.shyn/attempt']=token
        path=directory/'injection.yaml';path.write_text(yaml.safe_dump(manifest,sort_keys=False))
        record.update(resolved=details,chaos_parameters=manifest['spec'])
        resource=manifest['kind'].lower()+'/'+manifest['metadata']['name']
        state=snapshot();write(directory/'preflight-state.json',state)
        issues=health_issues(state)
        manifest_hash=hashlib.sha256((ROOT/'infra/sock-shop/local-emulated.yaml').read_bytes()).hexdigest()
        record['environment_manifest_sha256']=manifest_hash
        if issues:raise ValueError('Preflight blocked: '+', '.join(issues))
        if not args.stability_result:raise ValueError('--stability-result is required for execution')
        validate_receipt(args.stability_result,state,manifest_hash)
        if release_path:
            release=verify_release(release_path,ROOT,row['split'])
            record['dataset_role']='prospective_candidate'
            record['observation_policy']=release['observation']
        elif row['split']!='reference':raise ValueError('Only reference candidates may execute while protocol remains draft')
        kube('create','--dry-run=server','-f',str(path))
        try:write(directory/'collector-before.json',get('http://127.0.0.1:8000/incidents'))
        except Exception as exc:record['collector_before_error']=type(exc).__name__
        # Prime transport before synthetic traffic; no user credentials involved.
        import urllib.request
        urllib.request.urlopen('http://127.0.0.1:8080/',timeout=10).close()
        fault_seconds=row['duration_seconds'] if row['variant']!='pod-failure' else 30
        traffic_seconds=30+40+fault_seconds+35+15
        log=(directory/'traffic-process.log').open('w')
        start=time.time()
        traffic=subprocess.Popen([sys.executable,str(ROOT/'traffic/steady.py'),'--seconds',str(traffic_seconds),
            '--profile','checkout','--pause',str(row['traffic_pause_seconds']),'--seed',str(row['seed']),
            '--output',str(directory/'traffic.json')],stdout=log,stderr=subprocess.STDOUT)
        for _ in range(3):
            time.sleep(10);print('Healthy warmup',flush=True)
        warmup=json.loads((directory/'traffic.json').read_text())
        current=snapshot();write(directory/'warmup-state.json',current)
        if health_issues(current) or lifecycle(current)!=lifecycle(state) or warmup['failed_requests'] or not warmup['completed_journeys']:
            raise ValueError('Baseline changed or healthy warmup checkout failed; no injection')
        record.update(execution_status='creating',injection_requested_at=now());checkpoint()
        possible_create=True
        kube('create','-f',str(path))
        for _ in range(20):
            status=kube_json('sock-shop','get',resource)
            write(directory/'chaos-status.json',status)
            if any(c.get('type')=='AllInjected' and c.get('status')=='True' for c in status.get('status',{}).get('conditions',[])):
                break
            time.sleep(2)
        else:raise RuntimeError('Controller did not confirm AllInjected')
        record.update(execution_status='injected',injection_confirmed_at=now());checkpoint()
        print('Injected '+row['scenario_id']+'; not admitted',flush=True)
        fault_started=time.monotonic()
        end=fault_started+fault_seconds;counter_saved=False;node_samples=[]
        fault_clock=[{'at':now()}]
        while time.monotonic()<end:
            time.sleep(min(5,max(0,end-time.monotonic())))
            from app.experiment_runtime import read_cgroup
            group=read_cgroup()
            if release:
                fault_clock.append({'at':now()})
                record['fault_temporal_check']=audit_timing(fault_clock,time.monotonic()-fault_started,5)
                if record['fault_temporal_check']['status']!='passed':
                    raise RuntimeError('UTC discontinuity during fault; abort and retain failed attempt')
            node_samples.append({'at':now(),'node_cgroup':group})
            write(directory/'node-during-fault.json',node_samples)
            if group['events']['oom_kill']>state['node_cgroup']['events']['oom_kill']:
                raise RuntimeError('Node-local OOM during fault; abort and review collateral impact')
            if group['full_pressure']['avg10']>5:
                raise RuntimeError('Node memory stall during fault; abort')
            if row['variant'].startswith('network-') and not counter_saved and end-time.monotonic()<=fault_seconds/2:
                try:capture_qdisc(directory/'network-counters.json',source=details['source_service'])
                except Exception as exc:record['network_counter_error']=str(exc)
                counter_saved=True
            print('Fault observation: '+str(max(0,int(end-time.monotonic())))+'s',flush=True)
    except (Exception,KeyboardInterrupt) as exc:
        record.update(execution_status='failed' if possible_create else 'preflight_failed',
                      error_type=type(exc).__name__,error=str(exc));checkpoint()
    finally:
        if possible_create:
            try:
                owned=json.loads(kube('get',resource,'--ignore-not-found','-o','json') or '{}')
                if owned:
                    if owned['metadata'].get('labels',{}).get('thesis.shyn/attempt')!=token:
                        raise RuntimeError('Cleanup refused: resource ownership mismatch')
                    kube('delete',resource,'--wait=true','--timeout=25s')
                record['cleanup_completed_at']=now()
            except Exception as exc:record['cleanup_error']=str(exc)
            checkpoint()
        if traffic:
            try:
                for _ in range(7):time.sleep(5)
                traffic.wait(timeout=90)
                record['traffic_exit_code']=traffic.returncode
                record['capture']=capture(start,time.time(),directory/'telemetry')
                after=snapshot();write(directory/'recovery-state.json',after)
                record['recovery_issues']=health_issues(after)
                record['recovered_at']=now()
                try:
                    rows=get('http://127.0.0.1:8000/incidents')
                    write(directory/'collector-after.json',rows)
                    details=[]
                    for item in rows:
                        if not re.fullmatch(r'INC-\d{8}T\d{6}-[a-f0-9]{8}',item.get('id','')):continue
                        received=dt.datetime.fromisoformat(item['received_at'].replace('Z','+00:00')).timestamp()
                        if start<=received<=time.time():
                            details.append(get('http://127.0.0.1:8000/incidents/'+item['id']))
                    write(directory/'collector-window.json',details)
                    record['collector_window_incidents']=len(details)
                except Exception as exc:record['collector_after_error']=type(exc).__name__
            except Exception as exc:record['recovery_or_capture_error']=str(exc)
            finally:
                if traffic.poll() is None:
                    traffic.terminate()
                    try:traffic.wait(timeout=15)
                    except subprocess.TimeoutExpired:traffic.kill();traffic.wait(timeout=5)
        if log:log.close()
        record['finished_at']=now();checkpoint()
    quality=record.get('capture',{}).get('quality',{})
    completed=(record['execution_status']=='injected' and record.get('cleanup_completed_at')
        and not record.get('cleanup_error') and record.get('traffic_exit_code')==0
        and not record.get('recovery_issues') and 'recovery_or_capture_error' not in record
        and all(quality.get(k) for k in ('metrics_present','logs_present','traces_present'))
        and not quality.get('log_export_incomplete') and not quality.get('trace_limit_reached')
        and not record.get('capture',{}).get('errors'))
    if completed:
        record['execution_status']='captured_requires_review'
        if release:
            try:
                anchor=dt.datetime.fromisoformat(record['injection_confirmed_at']).timestamp()
                record['observation_capture']=crop(directory/'telemetry',directory/'observation/telemetry',anchor-30,anchor+30)
                if not all(record['observation_capture']['quality'][key] for key in ('metrics_present','logs_present','traces_present')):
                    raise ValueError('Precommitted observation missing a modality')
            except Exception as exc:
                completed=False;record['execution_status']='failed_observation'
                record['observation_error']=type(exc).__name__+': '+str(exc)
        checkpoint()
    if release:
        record['finished_at']=now();checkpoint()
    print(json.dumps({'path':str(directory),'status':record['execution_status'],
        'admission_status':record['admission_status'],'error':record.get('error')},indent=2),flush=True)
    return 0 if completed else 1


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--plan',type=Path,default=ROOT/'experiments/scenario-plan.json')
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--render-all',action='store_true')
    group.add_argument('--scenario-id')
    parser.add_argument('--server-dry-run',action='store_true')
    parser.add_argument('--server-dry-run-all',action='store_true',help='Validate all 200 manifests without injecting')
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--stability-result',type=Path)
    parser.add_argument('--collection-release',type=Path,help='Precommitted source/window policy; does not admit cases')
    args=parser.parse_args()
    plan=json.loads(args.plan.read_text())
    if audit(plan)['errors']:raise ValueError('Plan failed structural audit')
    plan_hash=hashlib.sha256(args.plan.read_bytes()).hexdigest()
    with experiment_lock():
        if args.render_all:
            if args.execute:parser.error('Cannot execute all scenarios at once')
            return prepare_all(plan,plan_hash,args)
        row=next((r for r in plan['scenarios'] if r['scenario_id']==args.scenario_id),None)
        if row is None:parser.error('Unknown scenario ID')
        if not args.execute:
            deployments,services=inventory()
            manifest,details=render(row,deployments,services,'prepared-'+row['scenario_id'].lower())
            print(yaml.safe_dump(manifest,sort_keys=False));print(json.dumps(details,indent=2))
            return 0
        def stop(*_):raise KeyboardInterrupt('Interrupted; cleaning up owned chaos resource')
        signal.signal(signal.SIGTERM,stop)
        signal.signal(signal.SIGINT,stop)
        return execute_one(plan,plan_hash,row,args)


if __name__=='__main__':raise SystemExit(main())
