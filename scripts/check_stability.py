#!/usr/bin/env python3
"""Bounded local development soak with synthetic checkout, never an LLM call."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.experiment_runtime import experiment_lock,read_cgroup
from app.stability_timing import audit_timing,VERSION as TIMING_VERSION


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--seconds', type=int, default=300)
    parser.add_argument('--interval', type=int, default=30)
    args = parser.parse_args()
    if not 60<=args.seconds<=600 or args.interval < 5:
        parser.error('Use 60..600 seconds and at least a 5 second interval; longer checks need a segmented soak')
    os.chdir(ROOT)
    directory = ROOT/'results/stability'/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    directory.mkdir(parents=True)
    kube = ['kubectl', '--kubeconfig', str(ROOT/'.runtime/kubeconfig'), '--context', 'shyn-thesis']

    def read(*arguments):
        return json.loads(subprocess.run(kube+list(arguments)+['-o', 'json'], check=True,
                          capture_output=True, text=True, timeout=20).stdout)

    def sample():
        pods = read('-n', 'sock-shop', 'get', 'pods')['items']
        nodes = read('get', 'nodes')['items']
        faults = read('-n', 'sock-shop', 'get', 'stresschaos,networkchaos,podchaos')['items']
        support = [p for namespace in ('monitoring', 'chaos-mesh')
                   for p in read('-n', namespace, 'get', 'pods')['items']]
        return {'at': dt.datetime.now(dt.timezone.utc).isoformat(), 'chaos_count': len(faults),
                'node_cgroup':read_cgroup(),
                'nodes': {n['metadata']['name']: {c['type']: c['status'] for c in n['status']['conditions']} for n in nodes},
                'pods': {p['metadata']['name']: {'uid': p['metadata']['uid'],
                    'ready': any(c['type']=='Ready' and c['status']=='True' for c in p['status'].get('conditions', [])),
                    'restarts': {c['name']: c['restartCount'] for c in p['status'].get('containerStatuses', [])}}
                    for p in pods},
                'support_pods': {p['metadata']['namespace']+'/'+p['metadata']['name']: {
                    'uid': p['metadata']['uid'],
                    'ready': any(c['type']=='Ready' and c['status']=='True' for c in p['status'].get('conditions', [])),
                    'restarts': {c['name']: c['restartCount'] for c in p['status'].get('containerStatuses', [])}}
                    for p in support}}

    samples = []
    issues = []
    traffic = None
    completed = False
    started = time.monotonic()
    traffic_log = (directory/'traffic-process.log').open('w')
    try:
        # A healthy Pod does not imply that the local port-forward is ready.
        # Refuse traffic before sampling Kubernetes if the tunnel is unavailable.
        try:
            with urllib.request.urlopen('http://127.0.0.1:8080/',timeout=5) as response:
                if response.status!=200:raise RuntimeError('Frontend HTTP status is not200')
        except Exception as exc:
            raise RuntimeError('Frontend tunnel unavailable; no soak traffic started') from exc
        first = sample()
        samples.append(first)
        if first['chaos_count'] or not first['pods'] or not all(p['ready'] for p in first['pods'].values()):
            raise RuntimeError('Refuse soak: application not Ready or existing chaos resource')
        if not first['support_pods'] or not all(p['ready'] for p in first['support_pods'].values()):
            raise RuntimeError('Refuse soak: monitoring/chaos support Pods not Ready')
        if first['node_cgroup']['working_set_bytes']/first['node_cgroup']['memory_max_bytes']>.95:
            raise RuntimeError('Refuse soak: node has less than 5% working-set headroom')
        traffic = subprocess.Popen([sys.executable, str(ROOT/'traffic/steady.py'), '--seconds', str(args.seconds),
                    '--pause', '1.5', '--profile', 'checkout', '--output', str(directory/'traffic.json')],
                    stdout=traffic_log, stderr=subprocess.STDOUT)
        while True:
            time.sleep(min(args.interval, max(0, args.seconds-(time.monotonic()-started))))
            current = sample()
            samples.append(current)
            gap=(dt.datetime.fromisoformat(current['at'])-dt.datetime.fromisoformat(samples[-2]['at'])).total_seconds()
            if gap<0 or gap>max(60,3*args.interval):
                issues.append({'reason':'utc_sampling_discontinuity','gap_seconds':gap})
                raise RuntimeError('UTC sampling gap or clock discontinuity; stop and review sleep/clock changes')
            for node, conditions in current['nodes'].items():
                if conditions.get('Ready') != 'True' or any(conditions.get(c)=='True' for c in ('MemoryPressure','DiskPressure','PIDPressure')):
                    issues.append({'at': current['at'], 'reason': 'node_unhealthy', 'node': node})
            if current['chaos_count']:
                issues.append({'at': current['at'], 'reason': 'unexpected_chaos'})
            if current['pods'] != first['pods']:
                issues.append({'at': current['at'], 'reason': 'pod_state_or_restart_changed'})
            if current['support_pods'] != first['support_pods']:
                issues.append({'at': current['at'], 'reason': 'support_pod_state_or_restart_changed'})
            if current['node_cgroup']['events']['oom_kill'] > first['node_cgroup']['events']['oom_kill']:
                issues.append({'at': current['at'], 'reason': 'node_cgroup_oom_kill'})
            if current['node_cgroup']['full_pressure']['avg10'] > 5:
                issues.append({'at': current['at'], 'reason': 'node_cgroup_memory_stall_above_5_percent'})
            if current['node_cgroup']['working_set_bytes']/current['node_cgroup']['memory_max_bytes']>.95:
                issues.append({'at':current['at'],'reason':'node_cgroup_working_set_headroom_below_5_percent'})
            (directory/'samples.json').write_text(json.dumps(samples, indent=2)+'\n')
            print(f"Soak {int(time.monotonic()-started)}s / {args.seconds}s; issues={len(issues)}", flush=True)
            if time.monotonic()-started >= args.seconds:
                break
        traffic.wait(timeout=45)
        if traffic.returncode:
            issues.append({'reason': 'traffic_process_failed'})
        data = json.loads((directory/'traffic.json').read_text())
        if data['failed_requests'] or not data['completed_journeys']:
            issues.append({'reason': 'checkout_failures_or_no_completed_journey'})
        completed = True
    except Exception as exc:
        issues.append({'reason': 'soak_error', 'error_type': type(exc).__name__, 'message': str(exc)})
    finally:
        if not completed:
            issues.append({'reason': 'incomplete_soak'})
        if traffic and traffic.poll() is None:
            traffic.terminate()
            traffic.wait(timeout=15)
        traffic_log.close()
        (directory/'samples.json').write_text(json.dumps(samples, indent=2)+'\n')
        timing=audit_timing(samples,time.monotonic()-started,args.interval)
        if timing['status']!='passed':issues.append({'reason':'temporal_gate_failed','details':timing})
        result = {'status': 'passed_short_soak' if not issues else 'failed', 'requested_seconds': args.seconds,
                  'health_gate_version':'cgroup-working-set-v1',
                  'temporal_gate_version':TIMING_VERSION,'sampling_interval_seconds':args.interval,'temporal_check':timing,
                  'finished_at':dt.datetime.now(dt.timezone.utc).isoformat(),
                  'elapsed_seconds': time.monotonic()-started, 'sample_count': len(samples), 'issues': issues,
                  'manifest_sha256': hashlib.sha256((ROOT/'infra/sock-shop/local-emulated.yaml').read_bytes()).hexdigest(),
                  'limitation': 'Short development soak only; not long-term stability or official dataset admission.'}
        (directory/'result.json').write_text(json.dumps(result, indent=2)+'\n')
        print(json.dumps({'directory': str(directory), **result}, indent=2), flush=True)
    return 1 if issues else 0


if __name__ == '__main__':
    with experiment_lock():raise SystemExit(main())
