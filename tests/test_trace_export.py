import unittest
from unittest.mock import patch
import datetime as dt
from app.telemetry import query_traces


class TraceExportTests(unittest.TestCase):
    def setUp(self):
        setting=patch.dict("os.environ", {"TRACE_FRONTEND_ENABLED":"false"})
        setting.start();self.addCleanup(setting.stop)

    def test_frontend_profiles_are_explicit_and_bounded(self):
        with patch.dict("os.environ", {"TRACE_FRONTEND_ENABLED":"true"}):
            result=query_traces(lambda *_: {}, "http://local", 0, 60)
        meta=result["export_metadata"]
        self.assertEqual(meta["queried_services"], ["front-end","orders","user"])
        self.assertEqual(meta["query_count"],7)
        self.assertEqual(len(meta["query_profiles"]),7)
        self.assertFalse(meta["incomplete"])

    def test_dense_windows_are_split_without_dropping_boundary_traces(self):
        def fetch(url,params):
            start=dt.datetime.fromisoformat(params['query.start_time_min']).timestamp()
            end=dt.datetime.fromisoformat(params['query.start_time_max']).timestamp()
            ids=[i for i in range(12) if start<=i<=end][:params['query.num_traces']]
            return {'result':{'resourceSpans':[{'scopeSpans':[{'spans':[
                {'traceId':'trace-'+str(i),'spanId':'span-'+str(i)} for i in ids]}]}]}}
        result=query_traces(fetch,'http://local',0,11,limit=3)
        self.assertEqual(result['export_metadata']['unique_spans'],12)
        self.assertFalse(result['export_metadata']['incomplete'])
        self.assertGreater(result['export_metadata']['query_count'],2)
    def test_shared_rpc_id_in_different_services_preserves_both_observations(self):
        def fetch(url,params):
            return {'result':{'resourceSpans':[
                {'resource':{'attributes':[{'key':'service.name','value':{'stringValue':service}}]},
                 'scopeSpans':[{'spans':[{'traceId':'same-trace','spanId':'same-rpc'}]}]}
                for service in ('front-end','user')]}}
        result=query_traces(fetch,'http://local',0,60)
        self.assertEqual(result['export_metadata']['unique_spans'],2)

    def test_multi_service_queries_deduplicate_shared_spans(self):
        def fetch(url,params):
            service=params['query.service_name']
            spans=[{'traceId':'trace','spanId':'shared'}]
            if service=='user':spans.append({'traceId':'user-trace','spanId':'user-span'})
            return {'result':{'resourceSpans':[{'scopeSpans':[{'spans':spans}]}]}}
        result=query_traces(fetch,'http://local',0,60)
        self.assertEqual(result['export_metadata']['unique_spans'],2)
        self.assertFalse(result['export_metadata']['incomplete'])

    def test_one_query_error_or_limit_is_not_silently_complete(self):
        def fetch(url,params):
            if params['query.service_name']=='user':raise RuntimeError('unavailable')
            return {'result':{'resourceSpans':[{'scopeSpans':[{'spans':[{'traceId':'trace','spanId':'span'}]}]}]}}
        result=query_traces(fetch,'http://local',0,60,limit=1)
        self.assertTrue(result['export_metadata']['incomplete'])
        self.assertIn('user',result['export_metadata']['query_errors'])
