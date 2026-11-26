"""Scope a MySQL startup configuration to the local catalogue database."""
import copy
import hashlib

NAME='shyn-mysql-memory'
CONFIG_PATH='/etc/mysql/conf.d/shyn-memory.cnf'


def apply_mysql_policy(documents,config):
    rows=copy.deepcopy(documents)
    targets=[r for r in rows if r.get('kind')=='Deployment' and r['metadata']['name']=='catalogue-db']
    if len(targets)!=1 or targets[0]['metadata'].get('namespace')!='sock-shop':raise ValueError('Expected one sock-shop catalogue-db')
    target=targets[0];template=target['spec']['template'];spec=template['spec'];containers=spec['containers']
    if len(containers)!=1 or containers[0]['name']!='catalogue-db':raise ValueError('Unexpected MySQL container layout')
    container=containers[0]
    readiness={'tcpSocket':{'port':3306},'initialDelaySeconds':2,'periodSeconds':2,'timeoutSeconds':2,'failureThreshold':60}
    if container.get('readinessProbe',readiness)!=readiness:raise ValueError('Refuse to replace an unrelated readiness probe')
    container['readinessProbe']=readiness
    if any(v.get('mountPath')==CONFIG_PATH and v['name']!=NAME for v in container.get('volumeMounts',[])):
        raise ValueError('Refuse to replace an unrelated configuration mount')
    digest=hashlib.sha256(config.encode()).hexdigest()
    template.setdefault('metadata',{}).setdefault('annotations',{})['thesis.shyn/mysql-memory-sha256']=digest
    spec['volumes']=[v for v in spec.get('volumes',[]) if v['name']!=NAME]+[
        {'name':NAME,'configMap':{'name':NAME,'defaultMode':292}}]
    container['volumeMounts']=[v for v in container.get('volumeMounts',[]) if v['name']!=NAME]+[
        {'name':NAME,'mountPath':CONFIG_PATH,'subPath':'shyn-memory.cnf','readOnly':True}]
    rows=[r for r in rows if not (r.get('kind')=='ConfigMap' and r['metadata']['name']==NAME)]
    rows.append({'apiVersion':'v1','kind':'ConfigMap','metadata':{'name':NAME,'namespace':'sock-shop',
        'annotations':{'thesis.shyn/source-sha256':digest}},'data':{'shyn-memory.cnf':config}})
    return rows
