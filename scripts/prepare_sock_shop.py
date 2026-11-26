#!/usr/bin/env python3
"""Generate an explicitly emulated, digest-pinned local Sock Shop manifest."""
import argparse
import hashlib
import json
from pathlib import Path
import yaml
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.db_cache_policy import apply_policy
from app.mysql_policy import apply_mysql_policy
from app.frontend_tracing_policy import apply_frontend_tracing


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=ROOT/'infra/sock-shop/local-emulated.yaml')
    parser.add_argument('--db-cache-hook',action='store_true',help='Render the staged hook; does not deploy it')
    parser.add_argument('--mysql-memory-policy',action='store_true',help='Render the staged MySQL policy; does not deploy it')
    parser.add_argument('--frontend-tracing',action='store_true',help='Render staged frontend tracing; does not deploy it')
    args=parser.parse_args()
    source = ROOT / 'infra/sock-shop/upstream.yaml'
    expected = '02d70d2c7b576ea8b18fc436e18b9158d5b662e50180998b82127d8050813771'
    if hashlib.sha256(source.read_bytes()).hexdigest() != expected:
        raise ValueError('Upstream manifest changed; review provenance before generation')
    entries = []
    for name in ['image-audit.json', 'legacy-db-audit.json']:
        entries.extend(json.loads((ROOT / 'results/environment' / name).read_text())['images'])
    audited = {e['image']: e for e in entries}
    native_path=ROOT/'infra/native/active-images.json'
    native_state=json.loads(native_path.read_text()) if native_path.exists() else {}
    native=native_state.get('services',{}) if native_state.get('enabled') else {}
    overrides = {'mongo': 'mongo:3.4.24', 'redis:alpine': 'redis:4.0.14-alpine'}
    documents = list(yaml.safe_load_all(source.read_text()))
    lock = {}
    for doc in documents:
        if doc['kind'] == 'Deployment':
            doc['spec']['strategy'] = {'type': 'Recreate'}
            pod = doc['spec']['template']['spec']
            pod['nodeSelector'] = {'kubernetes.io/os': 'linux'}
            for c in pod['containers']:
                original = c['image']
                chosen = overrides.get(original, original)
                proof = audited[chosen]
                if proof['status'] != 'ok' or not proof.get('digest'):
                    raise ValueError(f'Unresolved image: {chosen}')
                repo = chosen.rsplit(':', 1)[0] if ':' in chosen else chosen
                c['image'] = f"{repo}@{proof['digest']}"
                lock[original] = {'selected_tag': chosen, 'pinned_image': c['image'], 'arm64_native': proof['arm64_native']}
                service=doc['metadata']['name']
                if service in native:
                    selected=native[service]
                    if selected['architecture']!='arm64' or selected['os']!='linux' or not selected['binary_sha256']:
                        raise ValueError('Invalid native image metadata')
                    c['image']=selected['tag'];c['imagePullPolicy']='Never'
                    lock[original]['native_override']=selected
                    lock[original]['arm64_native']=True
                    pod_annotations=doc['spec']['template'].setdefault('metadata',{}).setdefault('annotations',{})
                    pod_annotations.update({'thesis.shyn/source-commit':selected['source_commit'],
                        'thesis.shyn/binary-sha256':selected['binary_sha256'],'thesis.shyn/execution-mode':'native-arm64-go1.23.12'})
                    if service=='user':
                        env={e['name']:e for e in c.get('env',[])}
                        for name,value in {'USER_DATABASE':'mongodb','MONGO_HOST':'user-db','HATEAOS':'user',
                            'ZIPKIN':'http://jaeger.monitoring.svc.cluster.local:9411/api/v1/spans'}.items():
                            env[name]={'name':name,'value':value}
                        c['env']=list(env.values())
                if 'readinessProbe' in c:
                    c['readinessProbe']['initialDelaySeconds'] = 5
                    c['readinessProbe'].update(timeoutSeconds=3, periodSeconds=5)
                if 'livenessProbe' in c:
                    # The emulated Go services previously restarted during brief
                    # node contention with Kubernetes' default 1s timeout.
                    c['livenessProbe'].update(timeoutSeconds=3, periodSeconds=10, failureThreshold=6)
                if doc['metadata']['name'] == 'user':
                    # A background OOM at 200Mi was observed outside chaos.
                    # Keep this development adjustment separate from old pilots.
                    c['resources']['limits']['memory'] = '384Mi'
                if doc['metadata']['name'] == 'catalogue':
                    # Healthy checkout saturated both upstream 200m/200Mi caps
                    # in the second soak, independently of node-level OOM.
                    c['resources']['limits'].update(cpu='500m', memory='384Mi')
                if doc['metadata']['name'] in ('carts', 'orders', 'shipping'):
                    c['readinessProbe'] = {'httpGet': {'path': '/health', 'port': 80},
                                           'initialDelaySeconds': 10, 'periodSeconds': 5,
                                           'timeoutSeconds': 3, 'failureThreshold': 3}
                    c['resources']['limits']['cpu'] = '1000m'
                    for env in c.get('env', []):
                        if env['name'] == 'JAVA_OPTS':
                            env['value'] = env['value'].replace('-Dspring.zipkin.enabled=false', '-Dspring.zipkin.enabled=true')
                            env['value'] += ' -Dspring.zipkin.base-url=http://jaeger.monitoring.svc.cluster.local:9411 -Dspring.sleuth.sampler.percentage=1.0 -XX:TieredStopAtLevel=1'
                if doc['metadata']['name'] in ('payment', 'catalogue'):
                    c['command'] = ['/app']
                    c['args'] = ['-port=80', '-zipkin=http://jaeger.monitoring.svc.cluster.local:9411/api/v1/spans']
                if 'resources' not in c:
                    c['resources'] = {
                        'requests': {'cpu': '50m', 'memory': '64Mi'},
                        'limits': {'cpu': '500m', 'memory': '512Mi'},
                    }
            doc['metadata'].setdefault('annotations', {})['thesis.shyn/execution-mode'] = (
                'mixed-native-go-arm64-and-amd64-emulation' if native else 'mixed-arm64-amd64-emulation')
        elif doc['kind'] == 'Service' and doc['metadata']['name'] == 'front-end':
            doc['spec']['type'] = 'ClusterIP'
            for port in doc['spec']['ports']:
                port.pop('nodePort', None)
    policy_path=ROOT/'infra/sock-shop/db-cache-policy.json'
    policy=json.loads(policy_path.read_text()) if policy_path.exists() else {}
    if args.db_cache_hook or policy.get('enabled'):
        documents=apply_policy(documents,(ROOT/'infra/sock-shop/db-cache-init.sh').read_text())
    mysql_path=ROOT/'infra/sock-shop/mysql-memory-policy.json'
    mysql_policy=json.loads(mysql_path.read_text()) if mysql_path.exists() else {}
    if args.mysql_memory_policy or mysql_policy.get('enabled'):
        documents=apply_mysql_policy(documents,(ROOT/'infra/sock-shop/mysql-memory.cnf').read_text())
    frontend_path=ROOT/'infra/tracing/frontend-policy.json'
    frontend=json.loads(frontend_path.read_text()) if frontend_path.exists() else {}
    if args.frontend_tracing or frontend.get('enabled'):
        documents=apply_frontend_tracing(documents,(ROOT/'infra/tracing/frontend-tracing.js').read_text())
    destination = args.output
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(yaml.safe_dump_all(documents, sort_keys=False))
    lock_path=ROOT/'infra/sock-shop/images.lock.json' if destination.resolve()==(ROOT/'infra/sock-shop/local-emulated.yaml').resolve() else destination.with_suffix('.images-lock.json')
    lock_path.write_text(json.dumps(lock, indent=2) + '\n')
    print(f'Generated {len(documents)} resources, {len(lock)} pinned image mappings: {destination}')


if __name__ == '__main__':
    main()
