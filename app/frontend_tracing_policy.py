"""Mount a versioned Node6-compatible tracer into the existing frontend image."""
import copy
import hashlib

NAME='shyn-frontend-tracing'
COMMAND=['node','--require','/opt/shyn-tracing/frontend-tracing.js','server.js']


def apply_frontend_tracing(documents,script):
    rows=copy.deepcopy(documents)
    targets=[r for r in rows if r.get('kind')=='Deployment' and r['metadata']['name']=='front-end']
    if len(targets)!=1 or targets[0]['metadata'].get('namespace')!='sock-shop':raise ValueError('Expected one local frontend')
    template=targets[0]['spec']['template'];spec=template['spec'];containers=spec['containers']
    if len(containers)!=1 or containers[0]['name']!='front-end':raise ValueError('Unexpected frontend container layout')
    container=containers[0]
    if container.get('command',COMMAND)!=COMMAND or container.get('args',[])!=[]:raise ValueError('Custom frontend entrypoint requires review')
    if container.get('workingDir','/usr/src/app')!='/usr/src/app':raise ValueError('Unexpected frontend working directory')
    container.update(command=list(COMMAND),args=[],workingDir='/usr/src/app')
    env={e['name']:e for e in container.get('env',[])}
    env['SHYN_ZIPKIN_URL']={'name':'SHYN_ZIPKIN_URL','value':'http://jaeger.monitoring.svc.cluster.local:9411/api/v1/spans'}
    container['env']=list(env.values())
    container['volumeMounts']=[m for m in container.get('volumeMounts',[]) if m['name']!=NAME]+[
        {'name':NAME,'mountPath':'/opt/shyn-tracing','readOnly':True}]
    spec['volumes']=[v for v in spec.get('volumes',[]) if v['name']!=NAME]+[{'name':NAME,'configMap':{'name':NAME,'defaultMode':292}}]
    digest=hashlib.sha256(script.encode()).hexdigest()
    template.setdefault('metadata',{}).setdefault('annotations',{})['thesis.shyn/frontend-tracing-sha256']=digest
    rows=[r for r in rows if not (r.get('kind')=='ConfigMap' and r['metadata']['name']==NAME)]
    rows.append({'apiVersion':'v1','kind':'ConfigMap','metadata':{'name':NAME,'namespace':'sock-shop',
        'annotations':{'thesis.shyn/source-sha256':digest}},'data':{'frontend-tracing.js':script}})
    return rows
