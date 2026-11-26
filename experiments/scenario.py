"""Resolve a planned scenario to a namespace-scoped Chaos Mesh manifest."""
from decimal import Decimal
import ipaddress
import re

CLASSES={'cpu':'Resource Exhaustion','memory':'Resource Exhaustion',
         'network-delay':'Network Delay / Packet Loss','network-loss':'Network Delay / Packet Loss',
         'pod-failure':'Pod Failure'}
TARGETS={'catalogue','payment','user','carts','orders','shipping'}
EDGES={('front-end','catalogue'),('front-end','user'),('front-end','carts'),('orders','payment'),('orders','shipping')}


def memory_bytes(quantity):
    match=re.fullmatch(r'([0-9]+(?:\.[0-9]+)?)(Ki|Mi|Gi|K|M|G)?',str(quantity))
    if not match:raise ValueError('Unsupported positive memory quantity')
    number,unit=match.groups()
    scale={None:1,'Ki':1024,'Mi':1024**2,'Gi':1024**3,'K':1000,'M':1000**2,'G':1000**3}[unit]
    value=int(Decimal(number)*scale)
    if value<=0:raise ValueError('Positive memory limit required')
    return value


def render(row,deployments,services,name):
    variant=row['variant'];target=row['target'];parameters=row['parameters']
    if variant not in CLASSES or row['fault_class']!=CLASSES[variant]:raise ValueError('Fault class mismatch')
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,62}',name):raise ValueError('Invalid resource name')
    if row['split'] not in ('reference','validation','test'):raise ValueError('Unknown split')
    if not 0<=row['traffic_pause_seconds']<=5:raise ValueError('Invalid traffic pause')
    if variant.startswith('network-'):
        if not isinstance(target,list) or tuple(target) not in EDGES:raise ValueError('Directed edge outside allowed topology')
        source,destination=target
    else:
        if target not in TARGETS:raise ValueError('Service outside allowed targets')
        source=target;destination=None
    if source not in deployments:raise ValueError('Target deployment missing')
    selector={'namespaces':['sock-shop'],'labelSelectors':{'name':source}}
    spec={'mode':'one','selector':selector}
    details={'source_service':source,'destination_service':destination}
    if variant=='pod-failure':
        if parameters!={'action':'pod-kill','replicas':1} or row['duration_seconds']!=0:raise ValueError('Unsupported Pod action')
        kind='PodChaos';spec['action']='pod-kill'
    else:
        duration=row['duration_seconds']
        if not isinstance(duration,int) or not 10<=duration<=120:raise ValueError('Duration must be 10..120s')
        spec['duration']=f'{duration}s'
        if variant=='cpu':
            workers=parameters['workers'];load=parameters['load_percent']
            if workers not in (1,2) or not 1<=load<=100:raise ValueError('Invalid CPU stress')
            kind='StressChaos';spec['stressors']={'cpu':{'workers':workers,'load':load}}
        elif variant=='memory':
            fraction=Decimal(str(parameters['additional_memory_fraction_of_declared_limit']))
            if not Decimal('.1')<=fraction<=Decimal('.8'):raise ValueError('Memory stress must be 10..80% of declared limit')
            containers=deployments[source]['spec']['template']['spec']['containers']
            if len(containers)!=1:raise ValueError('Explicit container selection required for multi-container service')
            limit=memory_bytes(containers[0]['resources']['limits']['memory'])
            size=int(fraction*limit)
            # memStress accepts a byte count. Never use a % of node memory.
            kind='StressChaos';spec['containerNames']=[containers[0]['name']]
            spec['stressors']={'memory':{'workers':1,'size':str(size)}}
            details.update(declared_memory_limit_bytes=limit,additional_memory_bytes=size)
        else:
            if destination not in deployments or destination not in services:raise ValueError('Destination missing')
            service=services[destination]
            if service['metadata'].get('namespace')!='sock-shop':raise ValueError('Wrong destination namespace')
            ip=service['spec'].get('clusterIP')
            if not ip or ip=='None' or not ipaddress.ip_address(ip).is_private:raise ValueError('Invalid destination ClusterIP')
            kind='NetworkChaos';spec.update(direction='to',target={'mode':'all','selector':{
                'namespaces':['sock-shop'],'labelSelectors':{'name':destination}}},externalTargets=[ip])
            if variant=='network-delay':
                latency=parameters['latency_ms'];jitter=parameters['jitter_ms']
                if not 1<=latency<=600 or not 0<=jitter<=100:raise ValueError('Invalid delay')
                spec.update(action='delay',delay={'latency':f'{latency}ms','jitter':f'{jitter}ms','correlation':'0'})
            else:
                loss=parameters['loss_percent']
                if not 1<=loss<=30:raise ValueError('Invalid loss')
                spec.update(action='loss',loss={'loss':str(loss),'correlation':'0'})
            details['destination_cluster_ip']=ip
    manifest={'apiVersion':'chaos-mesh.org/v1alpha1','kind':kind,
        'metadata':{'name':name,'namespace':'sock-shop','labels':{'thesis.shyn/managed-by':'scenario-runner'}},'spec':spec}
    return manifest,details
