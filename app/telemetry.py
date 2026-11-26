"""Bounded, time-split log export to avoid silently truncating dense windows."""
from collections import Counter
import datetime as dt
import json
import os
from pathlib import Path


def query_traces(getter,base,start,end,services=('orders','user'),limit=500,max_queries=32):
    """Merge observations across entry points without duplicating shared spans."""
    resources=[];seen=set();counts={};errors={};calls=0;incomplete=False
    profiles=[(service,None) for service in services]
    enabled=os.getenv('TRACE_FRONTEND_ENABLED')
    policy=Path(__file__).resolve().parents[1]/'infra/tracing/frontend-policy.json'
    frontend=(enabled.lower()=='true') if enabled is not None else (policy.exists() and json.loads(policy.read_text()).get('enabled',False))
    if frontend:
        profiles.extend(('front-end',operation) for operation in ('GET /catalogue','POST /cart','GET /cart','POST /orders','POST /register'))
    def fetch(service,operation,left,right,depth,trace_ids,label):
        nonlocal calls,incomplete
        if calls>=max_queries:
            incomplete=True;errors[label]='QueryBudgetExceeded';return
        try:
            calls+=1
            params={'query.service_name':service,'query.num_traces':limit,
                'query.start_time_min':dt.datetime.fromtimestamp(left,dt.timezone.utc).isoformat(),
                'query.start_time_max':dt.datetime.fromtimestamp(right,dt.timezone.utc).isoformat()}
            if operation:params['query.operation_name']=operation
            payload=getter(base+'/api/v3/traces',params)
            documents=payload if isinstance(payload,list) else [payload];batch_ids=set()
            for document in documents:
                for resource in document.get('result',{}).get('resourceSpans',[]):
                    for scope in resource.get('scopeSpans',[]):
                        batch_ids.update(s['traceId'] for s in scope.get('spans',[]) if s.get('traceId'))
            if len(batch_ids)>=limit:
                if right-left>.001 and depth<16 and calls+2<=max_queries:
                    middle=(left+right)/2
                    fetch(service,operation,left,middle,depth+1,trace_ids,label)
                    fetch(service,operation,middle,right,depth+1,trace_ids,label)
                    return
                incomplete=True
            for document in documents:
                for resource in document.get('result',{}).get('resourceSpans',[]):
                    service_name=next((a.get('value',{}).get('stringValue') for a in resource.get('resource',{}).get('attributes',[])
                                       if a.get('key')=='service.name'),'unknown') or 'unknown'
                    scopes=[]
                    for scope in resource.get('scopeSpans',[]):
                        spans=[]
                        for span in scope.get('spans',[]):
                            key=(service_name,span.get('traceId'),span.get('spanId'))
                            if all(key):trace_ids.add(key[1])
                            if not all(key) or key in seen:continue
                            seen.add(key);spans.append(span)
                        if spans:scopes.append({**scope,'spans':spans})
                    if scopes:resources.append({**resource,'scopeSpans':scopes})
        except Exception as exc:errors[label]=type(exc).__name__;incomplete=True
    for service,operation in profiles:
        label=service+(' '+operation if operation else '');trace_ids=set()
        fetch(service,operation,start,end,0,trace_ids,label);counts[label]=len(trace_ids)
    return {'result':{'resourceSpans':resources},'export_metadata':{'queried_services':sorted({p[0] for p in profiles}),
        'query_profiles':[{'service':s,'operation':op} for s,op in profiles],'query_count':calls,'max_queries':max_queries,
        'trace_counts_by_query':counts,'query_errors':errors,'unique_spans':len(seen),
        'per_query_limit':limit,'incomplete':incomplete}}


def query_logs(getter, base, start_ns, end_ns, page_limit=5000, max_pages=32):
    streams, calls, incomplete = {}, 0, False

    def fetch(start, end, depth=0):
        nonlocal calls, incomplete
        calls += 1
        result=getter(base+'/loki/api/v1/query_range', {'query':'{namespace="sock-shop"}',
            'start':start,'end':end,'limit':page_limit,'direction':'forward'})
        if result.get('status')!='success': raise ValueError('Loki query did not succeed')
        rows=result.get('data',{}).get('result',[])
        count=sum(len(row.get('values',[])) for row in rows)
        if count>=page_limit and end-start>1 and depth<20 and calls+2<=max_pages:
            middle=(start+end)//2
            fetch(start,middle,depth+1)
            fetch(middle,end,depth+1)
            return
        if count>=page_limit: incomplete=True
        for row in rows:
            key=tuple(sorted(row.get('stream',{}).items()))
            # Maximum multiplicity preserves repeated identical entries while
            # deduplicating overlap at interval boundaries.
            batch=Counter(tuple(v) for v in row.get('values',[]))
            existing=streams.setdefault(key,Counter())
            for value,multiplicity in batch.items(): existing[value]=max(existing[value],multiplicity)

    fetch(start_ns,end_ns)
    result=[]
    for labels,counts in sorted(streams.items()):
        values=[list(value) for value in sorted(counts,key=lambda v:(int(v[0]),v[1])) for _ in range(counts[value])]
        result.append({'stream':dict(labels),'values':values})
    return {'status':'success','data':{'resultType':'streams','result':result},
            'export_metadata':{'query_count':calls,'page_limit':page_limit,'incomplete':incomplete}}
