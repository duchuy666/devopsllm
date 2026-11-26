"""Build bounded context from explicitly allowed telemetry files only.

Never read ground-truth.json, scenario names, injection status or chaos YAML.
"""
import hashlib
import json
from pathlib import Path
import re
import statistics
import urllib.parse
from collections import Counter
from drain3 import TemplateMiner
from drain3.template_miner_config import TemplateMinerConfig

KNOWN_PEERS={'front-end','user','catalogue','carts','orders','payment','shipping',
    'user-db','catalogue-db','carts-db','orders-db','rabbitmq','session-db','queue-master'}


def observed_peer(attributes,span_kind):
    for attribute in attributes:
        key=attribute.get('key');value=attribute.get('value',{}).get('stringValue')
        if not isinstance(value,str) or len(value)>4096:continue
        if key!='peer.service' and not (span_kind=='client' and key in ('net.peer.name','http.host','http.url','url.full')):continue
        try:host=urllib.parse.urlsplit(value if '://' in value else '//'+value).hostname
        except ValueError:continue
        if not host:continue
        parts=host.lower().split('.')
        if parts[0] in KNOWN_PEERS and (len(parts)==1 or '.'.join(parts[1:]) in ('sock-shop','sock-shop.svc','sock-shop.svc.cluster.local')):
            return parts[0]
    return None


def redact(line):
    line = re.sub(r'''(?i)(authorization["'\s]*[:=]["'\s]*)(?:bearer|basic)\s+[^"'\s,}\]]+''', r'\1<REDACTED>', line)
    line = re.sub(r'thesis_\d+_\d+', '<TEST_USER>', line)
    line = re.sub(r'[\w.+-]+@[\w.-]+', '<EMAIL>', line)
    line = re.sub(r'\b[0-9a-f]{24}\b', '<OBJECT_ID>', line)
    line = re.sub(r'\b\d{12,19}\b', '<LONG_NUMBER>', line)
    line = re.sub(r'(?i)(password|authorization|api[_-]?key|ccv)([\s"\x27:=]+)[^\s,}\]]+', r'\1\2<REDACTED>', line)
    return line


def build_context(telemetry_dir, max_chars=24000):
    directory = Path(telemetry_dir)
    # The ID is derived only from observation content, never a fault-bearing path.
    permitted = {name: directory/name for name in ('metrics.json', 'logs.json', 'traces.json')}
    content_hash = hashlib.sha256()
    for name, path in permitted.items():
        content_hash.update(name.encode())
        if path.exists(): content_hash.update(path.read_bytes())
    context = {'schema_version': '0.4.1', 'incident_id': 'CTX-'+content_hash.hexdigest()[:16],
               'source_fingerprint':content_hash.hexdigest(),
               'selection_policy':'Preserve top two changing CPU/memory pods and their observed matching limits.',
               'metrics': [], 'logs': [], 'traces': [], 'missing_sources': [],
               'trace_selection_policy':'Up to eight observed client edges, then error/duration-ranked distinct operations; at most fifteen spans before budget trimming.',
               'coverage_note': 'Only instrumented services are visible. Runbook guidance does not prove an incident occurred.'}
    evidence = {}
    focus={'cpu':[],'memory':[]}
    protected=set()
    metrics_path = permitted['metrics.json']
    if metrics_path.exists():
        raw = json.loads(metrics_path.read_text())
        ordered=[(key,raw[key]) for key in ('cpu','memory') if key in raw]
        ordered.extend((key,value) for key,value in raw.items() if key not in ('cpu','memory'))
        for metric, payload in ordered:
            summaries = []
            for row in payload.get('response', {}).get('data', {}).get('result', []):
                points = [(float(t),float(v)) for t,v in row.get('values', []) if str(v) not in ('NaN','Inf','-Inf')]
                if not points: continue
                values = [value for _,value in points]
                baseline = statistics.mean(values[:max(1,len(values)//5)])
                summaries.append({'metric':metric,'pod':row.get('metric',{}).get('pod'),
                                  'service':row.get('metric',{}).get('service'),'route':row.get('metric',{}).get('route'),
                                  'min':min(values),'max':max(values),'mean':statistics.mean(values),
                                  'initial_window_mean':baseline,'max_minus_initial':max(values)-baseline,
                                  'window_start':points[0][0],'window_end':points[-1][0],
                                  'labels':row.get('metric',{})})
            summaries.sort(key=lambda r:r['max'] if metric=='created' else abs(r['max_minus_initial']), reverse=True)
            if metric in focus:
                focus[metric]=[r['pod'] for r in summaries[:2] if r.get('pod')]
            if metric in ('cpu_limit','memory_limit'):
                selected=focus[metric.removesuffix('_limit')]
                summaries.sort(key=lambda r:r['pod'] in selected,reverse=True)
            for summary in summaries[:8]:
                eid = f'E-M{len(context["metrics"])+1:03d}'
                summary['evidence_id'] = eid
                summary['unit'] = 'cores' if metric in ('cpu','cpu_limit') else ('bytes' if metric in ('memory','memory_limit') else ('unix_seconds' if metric=='created' else 'count_or_state'))
                if metric=='latency_mean':summary['unit']='seconds'
                if metric=='error_rate':summary['unit']='ratio'
                if metric=='request_rate':summary['unit']='requests_per_second'
                labels=summary.pop('labels')
                context['metrics'].append(summary)
                usage_kind=metric.removesuffix('_limit')
                if usage_kind in focus and summary['pod'] in focus[usage_kind]:protected.add(eid)
                evidence[eid] = {'source':'metrics.json','metric':metric,'labels':labels, 'query':payload.get('query')}
    else:
        context['missing_sources'].append('metrics')
    logs_path = permitted['logs.json']
    if logs_path.exists():
        config = TemplateMinerConfig()
        config.profiling_enabled = False
        miner = TemplateMiner(config=config)
        clusters = {}
        raw = json.loads(logs_path.read_text())
        for stream_index, stream in enumerate(raw.get('data',{}).get('result', [])):
            service = stream.get('stream',{}).get('service','unknown')
            for line_index,(timestamp,line) in enumerate(stream.get('values', [])):
                if re.search(r'Posting (Customer|Card|Address)',line,re.I): continue
                clean = redact(line)
                # Bound local work and preserve a short sample for evidence review.
                result = miner.add_log_message(clean[:1500])
                key = (service,result['cluster_id'])
                entry = clusters.setdefault(key,{'service':service,'template':result['template_mined'],
                    'count':0,'samples':[],'references':[], 'error_signal':False})
                entry['count'] += 1
                entry['template'] = result['template_mined']
                entry['error_signal'] |= bool(re.search(r'error|exception|timeout|refused|unavailable|oom|failed',clean,re.I))
                if len(entry['samples']) < 2:
                    entry['samples'].append({'timestamp':timestamp,'line':clean[:350]})
                    entry['references'].append({'stream_index':stream_index,'line_index':line_index})
        selected = sorted(clusters.values(),key=lambda e:(e['error_signal'],e['count']),reverse=True)[:15]
        for item in selected:
            eid=f'E-L{len(context["logs"])+1:03d}'
            references=item.pop('references')
            item['template']=item['template'][:350]
            item['evidence_id']=eid
            context['logs'].append(item)
            evidence[eid]={'source':'logs.json','references':references,'service':item['service']}
    else:
        context['missing_sources'].append('logs')
    traces_path = permitted['traces.json']
    if traces_path.exists():
        raw=json.loads(traces_path.read_text())
        documents=raw if isinstance(raw,list) else [raw]
        spans=[]
        for document in documents:
            for resource in document.get('result',{}).get('resourceSpans',[]):
                service=next((a.get('value',{}).get('stringValue') for a in resource.get('resource',{}).get('attributes',[]) if a.get('key')=='service.name'),'unknown')
                for scope in resource.get('scopeSpans',[]):
                    for span in scope.get('spans',[]):
                        start=int(span.get('startTimeUnixNano',0)); end=int(span.get('endTimeUnixNano',start))
                        spans.append({'service':service,'trace_id':span.get('traceId'),'span_id':span.get('spanId'),
                            'parent_span_id':span.get('parentSpanId'),'operation':span.get('name'),
                            'span_kind':{1:'internal',2:'server',3:'client',4:'producer',5:'consumer'}.get(span.get('kind')),
                            'duration_ms':max(0,end-start)/1e6,'status':span.get('status',{}),
                            'attributes':span.get('attributes',[])})
        spans.sort(key=lambda s:(s['status'].get('code')==2,s['duration_ms']),reverse=True)
        # Keep observed client edges before repeated slow root spans. Selection
        # uses telemetry only; no scenario target or ground truth is read.
        edges=[];seen_edges=set()
        for span in spans:
            peer=observed_peer(span['attributes'],span['span_kind'])
            edge=(span['service'],peer)
            if span['span_kind']=='client' and peer and edge not in seen_edges:
                edges.append(span);seen_edges.add(edge)
        selected=edges[:8];selected_ids={id(span) for span in selected};signatures=set()
        for span in selected:
            signatures.add((span['service'],span['operation'],span['span_kind']))
        for span in spans:
            signature=(span['service'],span['operation'],span['span_kind'])
            if id(span) not in selected_ids and signature not in signatures and len(selected)<15:
                selected.append(span);selected_ids.add(id(span));signatures.add(signature)
        for span in spans:
            if len(selected)>=15:break
            if id(span) not in selected_ids:selected.append(span);selected_ids.add(id(span))
        for span in selected:
            eid=f'E-T{len(context["traces"])+1:03d}'
            span['evidence_id']=eid
            peer=observed_peer(span.get('attributes',[]),span.get('span_kind'))
            if peer:span['peer_service']=peer
            # Attributes can carry synthetic customer payloads; omit them from model context.
            span.pop('attributes')
            context['traces'].append(span)
            evidence[eid]={'source':'traces.json','service':span['service'],'trace_id':span['trace_id'],'span_id':span['span_id']}
    else:
        context['missing_sources'].append('traces')
    context['truncated']=False
    initial_counts={key:len(context[key]) for key in ('metrics','logs','traces')}
    context['character_budget']=max_chars
    context['dropped_evidence_counts']={key:0 for key in initial_counts}
    for key in ('metrics','logs','traces'):
        if not context[key] and key not in context['missing_sources']: context['missing_sources'].append(key)
    while len(json.dumps(context,ensure_ascii=False))>max_chars:
        choices=[]
        counts=Counter(item['metric'] for item in context['metrics'])
        indices=[i for i,item in enumerate(context['metrics'])
                 if counts[item['metric']]>1 and item['evidence_id'] not in protected]
        if indices: choices.append(('metrics',indices[-1]))
        choices.extend((key,len(context[key])-1) for key in ('logs','traces') if len(context[key])>1)
        if not choices: raise ValueError('Context budget cannot preserve modalities, metric types and priority resource pairs')
        key,index=max(choices,key=lambda choice:len(json.dumps(context[choice[0]],ensure_ascii=False)))
        removed=context[key].pop(index)
        evidence.pop(removed['evidence_id'],None)
        context['truncated']=True
        context['dropped_evidence_counts']={key:initial_counts[key]-len(context[key]) for key in initial_counts}
    # Identity includes the actual processed payload and configuration, so an
    # older report cannot silently attach to changed evidence or token budgets.
    canonical={k:v for k,v in context.items() if k!='incident_id'}
    context['incident_id']='CTX-'+hashlib.sha256(json.dumps(canonical,ensure_ascii=False,sort_keys=True).encode()).hexdigest()[:16]
    return context,evidence
