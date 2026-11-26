#!/usr/bin/env python3
"""One fault at a time in the dedicated testbed; keep intent separate from context."""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import yaml
from capture_window import capture
from capture_qdisc import capture_qdisc
from verify_telemetry import get

ROOT = Path(__file__).resolve().parents[1]
KUBE = ['kubectl', '--kubeconfig', str(ROOT/'.runtime/kubeconfig'), '--context', 'shyn-thesis', '-n', 'sock-shop']
SCENARIOS = {
    'cpu': ('pilot-cpu.yaml', 'Resource Exhaustion', 'payment'),
    'memory': ('pilot-memory.yaml', 'Resource Exhaustion', 'payment'),
    'network-delay': ('pilot-network-delay.yaml', 'Network Delay / Packet Loss', 'front-end -> catalogue'),
    'network-loss': ('pilot-network-loss.yaml', 'Network Delay / Packet Loss', 'front-end -> catalogue'),
    'pod-failure': ('pilot-pod-failure.yaml', 'Pod Failure', 'payment'),
}


def kubectl(*args, **kwargs):
    return subprocess.run(KUBE+list(args), text=True, capture_output=True, check=True, timeout=30, **kwargs).stdout


def timestamp():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def wait_seconds(seconds, phase):
    end = time.monotonic()+seconds
    while time.monotonic() < end:
        print(f'{phase}: {max(0, int(end-time.monotonic()))}s remaining', flush=True)
        time.sleep(min(15, max(0, end-time.monotonic())))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('scenario', choices=SCENARIOS)
    args = parser.parse_args()
    os.chdir(ROOT)
    now = dt.datetime.now(dt.timezone.utc)
    case_id = f'PILOT-{now.strftime("%Y%m%dT%H%M%S")}-{args.scenario}'
    directory = ROOT/'data/pilot'/case_id
    directory.mkdir(parents=True)
    filename, fault_class, target = SCENARIOS[args.scenario]
    manifest = next(d for d in yaml.safe_load_all((ROOT/'chaos'/filename).read_text()) if d)
    manifest['metadata']['name'] = 'pilot-'+now.strftime('%H%M%S')+'-'+args.scenario
    if args.scenario in ('network-delay','network-loss'):
        # Egress in the source Pod can see Service ClusterIP before DNAT rather
        # than the destination Pod IP. Include the actual Service IP explicitly.
        service=json.loads(kubectl('get','service','catalogue','-o','json'))
        ip=service['spec'].get('clusterIP')
        if not ip or ip=='None': raise RuntimeError('Catalogue Service has no ClusterIP')
        manifest['spec']['externalTargets']=[ip]
    kind, name = manifest['kind'], manifest['metadata']['name']
    resource = f'{kind.lower()}/{name}'
    # Refuse overlapping fault resources in the target namespace.
    for existing_kind in ('stresschaos', 'networkchaos', 'podchaos'):
        if json.loads(kubectl('get', existing_kind, '-o', 'json'))['items']:
            raise RuntimeError('Existing chaos resource found; review/cleanup before another pilot')
    before = json.loads(kubectl('get', 'pods', '-o', 'json'))
    if any(not any(c.get('type')=='Ready' and c.get('status')=='True' for c in p.get('status',{}).get('conditions',[]))
           for p in before['items']):
        raise RuntimeError('All application Pods must be Ready before pilot')
    ground_truth = {'incident_id': case_id, 'dataset_role': 'development_pilot', 'scenario': args.scenario,
                    'fault_type': fault_class, 'intended_target': target, 'chaos_parameters': manifest['spec'],
                    'started_at': timestamp(), 'status': 'preparing', 'admission_status': 'requires_review'}
    (directory/'pods-before.json').write_text(json.dumps(before)+'\n')
    (directory/'injection.yaml').write_text(yaml.safe_dump(manifest,sort_keys=False))
    try:
        # Validate admission before creating traffic or injecting any fault.
        kubectl('create','--dry-run=server','-f',str(directory/'injection.yaml'))
    except subprocess.CalledProcessError as exc:
        ground_truth.update(status='preflight_failed',error=exc.stderr[-4000:],finished_at=timestamp())
        (directory/'ground-truth.json').write_text(json.dumps(ground_truth,indent=2)+'\n')
        print('PILOT PREFLIGHT FAILED: '+exc.stderr[-1000:],flush=True)
        return 1
    traffic_log = (directory/'traffic-process.log').open('w')
    traffic = subprocess.Popen([sys.executable, str(ROOT/'traffic/steady.py'), '--seconds', '150',
                                '--profile', 'checkout', '--output', str(directory/'traffic.json')],
                               stdout=traffic_log, stderr=subprocess.STDOUT)
    created, start = False, time.time()
    try:
        wait_seconds(30, 'healthy warmup')
        if traffic.poll() is not None:
            raise RuntimeError('Traffic process stopped during warmup')
        ground_truth['injection_requested_at'] = timestamp()
        kubectl('create', '-f', str(directory/'injection.yaml'))
        created = True
        injected = False
        for _ in range(20):
            state = json.loads(kubectl('get', resource, '-o', 'json'))
            (directory/'chaos-status.json').write_text(json.dumps(state, indent=2)+'\n')
            conditions = state.get('status', {}).get('conditions', [])
            if any(c.get('type')=='AllInjected' and c.get('status')=='True' for c in conditions):
                injected = True
                break
            time.sleep(2)
        if not injected:
            raise RuntimeError('Controller did not confirm AllInjected; this is not a valid injected case')
        ground_truth['injection_confirmed_at'] = timestamp()
        ground_truth['status'] = 'injected'
        print(f'Injected {args.scenario}; ground truth stored separately at {directory}', flush=True)
        if args.scenario.startswith('network-'):
            wait_seconds(30,'fault observation')
            try:
                counters=capture_qdisc(directory/'network-counters.json')
                ground_truth['network_counter_capture']='ok'
                print('Network counters captured; max qdisc drops='+str(counters['max_reported_drops']),flush=True)
            except Exception as exc:
                ground_truth['network_counter_error']=str(exc)
                print('Network counter capture unavailable: '+type(exc).__name__,flush=True)
            wait_seconds(30,'fault observation')
        else:
            wait_seconds(60 if args.scenario!='pod-failure' else 30, 'fault observation')
    except Exception as exc:
        ground_truth['status'], ground_truth['error'] = 'failed', str(exc)
        if isinstance(exc,subprocess.CalledProcessError): ground_truth['command_stderr']=exc.stderr[-4000:]
        print(f'PILOT FAILED: {exc}', flush=True)
    finally:
        if created:
            try:
                kubectl('delete', resource, '--wait=true', '--timeout=25s')
                ground_truth['cleanup_completed_at'] = timestamp()
            except Exception as exc:
                ground_truth['cleanup_error'] = str(exc)
        wait_seconds(35, 'recovery observation')
        end = time.time()
        try:
            ground_truth['capture'] = capture(start, end, directory/'telemetry')
            after = json.loads(kubectl('get', 'pods', '-o', 'json'))
            (directory/'pods-after.json').write_text(json.dumps(after)+'\n')
            ground_truth['pods_ready_after'] = all(any(c.get('type')=='Ready' and c.get('status')=='True'
                for c in p.get('status',{}).get('conditions',[])) for p in after['items'])
        except Exception as exc:
            ground_truth['export_error'] = str(exc)
        try:
            (directory/'collector-incidents.json').write_text(json.dumps(get('http://127.0.0.1:8000/incidents'),indent=2)+'\n')
        except Exception as exc:
            # This supplemental snapshot must not be confused with failed raw
            # telemetry export. Internal webhook delivery is checked separately.
            ground_truth['collector_snapshot_error']=str(exc)
        ground_truth['finished_at'] = timestamp()
        (directory/'ground-truth.json').write_text(json.dumps(ground_truth,indent=2)+'\n')
        try:
            traffic.wait(timeout=45)
        except subprocess.TimeoutExpired:
            traffic.terminate()
            traffic.wait(timeout=20)
        traffic_log.close()
    print(json.dumps({'case': case_id, 'status': ground_truth['status'], 'path': str(directory),
                      'pods_ready_after': ground_truth.get('pods_ready_after')},indent=2),flush=True)
    exported=ground_truth.get('capture',{})
    quality=exported.get('quality',{})
    complete=all(quality.get(key) for key in ('metrics_present','logs_present','traces_present'))
    return 0 if (ground_truth['status']=='injected' and 'cleanup_error' not in ground_truth
        and ground_truth.get('pods_ready_after') and 'export_error' not in ground_truth
        and not exported.get('errors') and complete and not quality.get('log_export_incomplete')
        and not quality.get('trace_limit_reached')) else 1


if __name__ == '__main__':
    from app.experiment_runtime import experiment_lock
    with experiment_lock():raise SystemExit(main())
