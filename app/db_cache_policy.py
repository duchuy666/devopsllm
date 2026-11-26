"""Render the persistent cache hook without altering database entrypoints."""
import copy
import hashlib

TARGETS=('user-db','carts-db','orders-db')
NAME='shyn-db-cache-policy'


def apply_policy(documents,script):
    rows=copy.deepcopy(documents)
    targets={r['metadata']['name']:r for r in rows if r.get('kind')=='Deployment' and r['metadata']['name'] in TARGETS}
    if set(targets)!=set(TARGETS):raise ValueError('Expected all three local MongoDB deployments')
    digest=hashlib.sha256(script.encode()).hexdigest()
    for name,doc in targets.items():
        if doc['metadata'].get('namespace')!='sock-shop':raise ValueError('Database outside sock-shop')
        template=doc['spec']['template'];spec=template['spec'];containers=spec['containers']
        if len(containers)!=1 or containers[0]['name']!=name:raise ValueError('Unexpected database container layout')
        container=containers[0];hook={'exec':{'command':['sh','/opt/shyn-cache/init.sh']}}
        lifecycle=container.setdefault('lifecycle',{})
        if lifecycle.get('postStart',hook)!=hook:raise ValueError('Refuse to replace an existing postStart hook')
        lifecycle['postStart']=hook
        template.setdefault('metadata',{}).setdefault('annotations',{})['thesis.shyn/db-cache-hook-sha256']=digest
        spec['volumes']=[v for v in spec.get('volumes',[]) if v['name']!=NAME]+[
            {'name':NAME,'configMap':{'name':NAME,'defaultMode':292}}]
        container['volumeMounts']=[v for v in container.get('volumeMounts',[]) if v['name']!=NAME]+[
            {'name':NAME,'mountPath':'/opt/shyn-cache','readOnly':True}]
    rows=[r for r in rows if not (r.get('kind')=='ConfigMap' and r['metadata']['name']==NAME)]
    rows.append({'apiVersion':'v1','kind':'ConfigMap','metadata':{'name':NAME,'namespace':'sock-shop',
        'annotations':{'thesis.shyn/source-sha256':digest}},'data':{'init.sh':script}})
    return rows
