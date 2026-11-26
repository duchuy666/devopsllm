"""Local experiment controls, independent of all LLM/provider code."""
from contextlib import contextmanager
import fcntl
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
KUBE=['kubectl','--kubeconfig',str(ROOT/'.runtime/kubeconfig'),'--context','shyn-thesis']


@contextmanager
def experiment_lock():
    path=ROOT/'.runtime/experiment.lock'
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a+') as handle:
        try:
            fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError('Another soak or chaos experiment holds the project lock') from exc
        try:yield
        finally:fcntl.flock(handle,fcntl.LOCK_UN)


def kube_json(namespace,*args):
    if namespace not in ('sock-shop','monitoring','chaos-mesh',None):
        raise ValueError('Namespace outside this testbed')
    command=KUBE+(['-n',namespace] if namespace else [])+list(args)+['-o','json']
    return json.loads(subprocess.run(command,check=True,capture_output=True,text=True,timeout=30).stdout)


def read_cgroup():
    raw=subprocess.run(['docker','exec','shyn-thesis','cat',
        '/sys/fs/cgroup/memory.current','/sys/fs/cgroup/memory.max',
        '/sys/fs/cgroup/memory.events.local','/sys/fs/cgroup/memory.pressure'],
        check=True,capture_output=True,text=True,timeout=20).stdout.splitlines()
    events={line.split()[0]:int(line.split()[1]) for line in raw[2:] if len(line.split())==2}
    full=next(line for line in raw if line.startswith('full '))
    stat=subprocess.run(['docker','exec','shyn-thesis','cat','/sys/fs/cgroup/memory.stat'],
        check=True,capture_output=True,text=True,timeout=20).stdout
    memory_stat={k:int(v) for k,v in (line.split() for line in stat.splitlines())}
    inactive=memory_stat['inactive_file']
    return {'memory_current_bytes':int(raw[0]),'memory_max_bytes':int(raw[1]),
        'inactive_file_bytes':inactive,'working_set_bytes':max(0,int(raw[0])-inactive),
        'working_set_method':'memory.current_minus_inactive_file',
        'events':events,'events_source':'memory.events.local',
        'full_pressure':{k:float(v) for k,v in (part.split('=') for part in full.split()[1:])}}


def ready(pod):
    return any(c.get('type')=='Ready' and c.get('status')=='True' for c in pod.get('status',{}).get('conditions',[]))


def snapshot():
    pods=kube_json('sock-shop','get','pods')['items']
    support=[p for ns in ('monitoring','chaos-mesh') for p in kube_json(ns,'get','pods')['items']]
    nodes=kube_json(None,'get','nodes')['items']
    faults=kube_json('sock-shop','get','stresschaos,networkchaos,podchaos')['items']
    return {'pods':pods,'support_pods':support,'nodes':nodes,'chaos':faults,'node_cgroup':read_cgroup()}


def health_issues(state):
    issues=[]
    if not state['pods']:issues.append('application_pods_missing')
    if not state['support_pods']:issues.append('support_pods_missing')
    for pod in state['pods']+state['support_pods']:
        if not ready(pod):issues.append('pod_not_ready:'+pod['metadata']['name'])
    if not state['nodes']:issues.append('node_missing')
    for node in state['nodes']:
        conditions={c['type']:c['status'] for c in node['status']['conditions']}
        if conditions.get('Ready')!='True' or any(conditions.get(c)=='True' for c in ('MemoryPressure','DiskPressure','PIDPressure')):
            issues.append('node_unhealthy')
    if state['chaos']:issues.append('existing_chaos')
    group=state['node_cgroup']
    if group.get('working_set_bytes',group['memory_current_bytes'])/group['memory_max_bytes']>.95:
        issues.append('node_cgroup_less_than_5_percent_working_set_headroom')
    if group['full_pressure']['avg10']>5:issues.append('node_memory_stall_above_5_percent')
    return issues
