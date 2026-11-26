import json
from pathlib import Path
import tempfile
import unittest
from app.context_builder import build_context,redact,observed_peer


class ContextBoundaryTests(unittest.TestCase):
    def test_client_url_keeps_only_known_host_not_auth_or_query(self):
        attrs=[{'key':'http.url','value':{'stringValue':'http://someone:PRIVATE_SENTINEL@shipping/shipping?card=PRIVATE_SENTINEL'}}]
        self.assertEqual(observed_peer(attrs,'client'),'shipping')
        self.assertIsNone(observed_peer(attrs,'server'))
        self.assertIsNone(observed_peer([{'key':'peer.service','value':{'stringValue':'shipping.private.example.com'}}],'client'))
    def test_only_known_observed_peer_is_kept_without_sensitive_attributes(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp)
            raw={'result':{'resourceSpans':[{'resource':{'attributes':[{'key':'service.name','value':{'stringValue':'front-end'}}]},
                'scopeSpans':[{'spans':[{'traceId':'trace','spanId':'span','name':'http:/cart',
                    'startTimeUnixNano':'1000','endTimeUnixNano':'2000','attributes':[
                        {'key':'peer.service','value':{'stringValue':'carts'}},
                        {'key':'authorization','value':{'stringValue':'PRIVATE_SENTINEL'}}]}]}]}]}}
            (directory/'traces.json').write_text(json.dumps(raw));context,index=build_context(directory)
            self.assertEqual(context['schema_version'],'0.4.1');self.assertEqual(context['traces'][0]['peer_service'],'carts')
            self.assertNotIn('PRIVATE_SENTINEL',json.dumps(context));self.assertEqual(index[context['traces'][0]['evidence_id']]['service'],'front-end')
    def test_repeated_slow_roots_do_not_hide_observed_client_edges(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp)
            roots=[{'traceId':str(i),'spanId':str(i),'name':'POST /register','kind':2,
                    'startTimeUnixNano':'0','endTimeUnixNano':'1000000000'} for i in range(30)]
            clients=[{'traceId':'client-'+peer,'spanId':peer,'name':'http:/:route','kind':3,
                      'startTimeUnixNano':'0','endTimeUnixNano':'1000000','attributes':[
                          {'key':'peer.service','value':{'stringValue':peer}}]} for peer in ('carts','orders','user','catalogue')]
            raw={'result':{'resourceSpans':[{'resource':{'attributes':[{'key':'service.name','value':{'stringValue':'front-end'}}]},
                 'scopeSpans':[{'spans':roots+clients}]}]}}
            (directory/'traces.json').write_text(json.dumps(raw))
            context,index=build_context(directory)
            self.assertEqual({s.get('peer_service') for s in context['traces'] if s.get('peer_service')}, {'carts','orders','user','catalogue'})
            self.assertLessEqual(len(context['traces']),15)
            self.assertEqual(set(index),{s['evidence_id'] for s in context['traces']})

    def test_ground_truth_and_fault_bearing_paths_do_not_change_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp)
            (directory/'metrics.json').write_text(json.dumps({'cpu':{'query':'CPU_OBSERVATION',
                'response':{'data':{'result':[{'metric':{'pod':'observed-pod'},'values':[[1,'0.01'],[2,'0.2']]}]}}}}))
            first=build_context(directory)
            (directory/'ground-truth.json').write_text('{"expected_root_cause":"LEAK_SENTINEL"}')
            (directory/'injection.yaml').write_text('fault: LEAK_SENTINEL')
            second=build_context(directory)
            self.assertEqual(first,second)
            self.assertNotIn('LEAK_SENTINEL',json.dumps(second))
            self.assertTrue(second[0]['incident_id'].startswith('CTX-'))

    def test_authorization_value_is_redacted(self):
        for original in ['Authorization: Bearer SECRET_SENTINEL',
                         'Authorization: Basic SECRET_SENTINEL',
                         '{"Authorization":"Bearer SECRET_SENTINEL"}']:
            with self.subTest(original=original):
                text=redact(original)
                self.assertNotIn('SECRET_SENTINEL',text)
                self.assertIn('REDACTED',text)

    def test_metric_evidence_can_be_resolved(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp)
            (directory/'metrics.json').write_text(json.dumps({'cpu':{'query':'cpu_query',
                'response':{'data':{'result':[{'metric':{'pod':'observed-pod'},'values':[[1,'0.01'],[2,'0.2']]}]}}}}))
            context,index=build_context(directory)
            eid=context['metrics'][0]['evidence_id']
            self.assertEqual(index[eid]['query'],'cpu_query')
            self.assertEqual(index[eid]['labels']['pod'],'observed-pod')
            self.assertIn('logs',context['missing_sources'])

    def test_route_identity_and_units_survive_preprocessing(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp)
            (directory/'metrics.json').write_text(json.dumps({'latency_mean':{'query':'observed_latency',
                'response':{'data':{'result':[{'metric':{'service':'front-end','route':'/catalogue'},
                                               'values':[[1,'0.02'],[2,'1.2']]}]}}}}))
            context,_=build_context(directory)
            self.assertEqual(context['metrics'][0]['route'],'/catalogue')
            self.assertEqual(context['metrics'][0]['service'],'front-end')
            self.assertEqual(context['metrics'][0]['unit'],'seconds')
            alternate,_=build_context(directory,max_chars=25000)
            self.assertNotEqual(context['incident_id'],alternate['incident_id'])

    def test_busy_pods_keep_matching_limits_even_when_raw_limits_come_first(self):
        def payload(kind):
            rows=[]
            for i in range(20):
                end=(1 if i==19 else .9 if i==18 else .01) if kind=='cpu' else 1
                initial=.01 if kind=='cpu' else 1
                rows.append({'metric':{'pod':f'pod-{i:02d}'},'values':[[1,str(initial)],[2,str(end)]]})
            return {'query':kind,'response':{'data':{'result':rows}}}
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp)
            (directory/'metrics.json').write_text(json.dumps({'cpu_limit':payload('cpu_limit'),'cpu':payload('cpu')}))
            context,index=build_context(directory,max_chars=2500)
            self.assertTrue(context['truncated'])
            for pod in ['pod-18','pod-19']:
                for metric in ['cpu','cpu_limit']:
                    row=next(r for r in context['metrics'] if r['metric']==metric and r['pod']==pod)
                    self.assertEqual(index[row['evidence_id']]['labels']['pod'],pod)
            self.assertLessEqual(len(json.dumps(context,ensure_ascii=False)),2500)


if __name__=='__main__': unittest.main()
