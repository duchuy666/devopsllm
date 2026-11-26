import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from app.observation_window import crop
from app.collection_release import verify_release
from scripts.run_dataset_collection import batches


class ProspectiveCollectionTests(unittest.TestCase):
    def raw(self, root):
        raw=root/'raw';raw.mkdir()
        (raw/'capture.json').write_text(json.dumps({'window_start':0,'window_end':10,'errors':{},'quality':{}}))
        (raw/'metrics.json').write_text(json.dumps({'cpu':{'query':'observed_query','response':{'data':{'result':[
            {'metric':{'pod':'observed'},'values':[[0,'1'],[2,'2'],[4,'3'],[6,'4']]}]}}}}))
        (raw/'logs.json').write_text(json.dumps({'data':{'result':[{'stream':{},'values':[
            [str(i*10**9),str(i)] for i in (0,2,4,6)]}]},'export_metadata':{'incomplete':False}}))
        spans=[{'traceId':str(i),'spanId':str(i),'startTimeUnixNano':str(left*10**9),
                'endTimeUnixNano':str(right*10**9)} for i,(left,right) in enumerate([(2,3),(3,7),(0,2)])]
        (raw/'traces.json').write_text(json.dumps({'result':{'resourceSpans':[{'scopeSpans':[{'spans':spans}]}]},
                                                 'export_metadata':{'incomplete':False,'query_count':7}}))
        return raw

    def test_cutoff_excludes_future_samples_and_spans_not_completed_at_cutoff(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);raw=self.raw(root);before={p.name:p.read_bytes() for p in raw.iterdir()}
            receipt=crop(raw,root/'observation',1,5)
            metrics=json.loads((root/'observation/metrics.json').read_text())
            self.assertEqual(metrics['cpu']['response']['data']['result'][0]['values'],[[2,'2'],[4,'3']])
            traces=json.loads((root/'observation/traces.json').read_text())
            self.assertEqual([s['traceId'] for s in traces['result']['resourceSpans'][0]['scopeSpans'][0]['spans']],['0'])
            self.assertEqual(receipt['quality']['span_count'],1)
            self.assertEqual(before,{p.name:p.read_bytes() for p in raw.iterdir()})
            self.assertNotIn('query_count',traces['export_metadata'])

    def test_window_outside_raw_or_incomplete_export_cannot_be_certified(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);raw=self.raw(root)
            with self.assertRaisesRegex(ValueError,'does not cover'):crop(raw,root/'outside',-1,5)
            p=raw/'capture.json';r=json.loads(p.read_text());r['quality']['trace_limit_reached']=True;p.write_text(json.dumps(r))
            with self.assertRaisesRegex(ValueError,'incomplete'):crop(raw,root/'partial',1,5)
            self.assertFalse((root/'partial').exists())

    def test_observation_cannot_replace_existing_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);raw=self.raw(root);crop(raw,root/'out',1,5)
            with self.assertRaisesRegex(ValueError,'replace'):crop(raw,root/'out',1,5)

    def test_schedule_keeps_group_split_order_and_pod_failure_last(self):
        plan=json.loads((Path(__file__).resolve().parents[1]/'experiments/scenario-plan.json').read_text())
        schedule=batches(plan['scenarios']);rows={r['scenario_id']:r for r in plan['scenarios']}
        ordered=[rows[key] for group in schedule for key in group]
        self.assertEqual(len(ordered),200);self.assertEqual(len({r['scenario_id'] for r in ordered}),200)
        ranks={'reference':0,'validation':1,'test':2}
        self.assertEqual([ranks[r['split']] for r in ordered],sorted(ranks[r['split']] for r in ordered))
        for group in schedule:
            self.assertLessEqual(len(group),4);self.assertEqual(len({rows[key]['split'] for key in group}),1)
            for key in group[:-1]:self.assertNotEqual(rows[key]['variant'],'pod-failure')

    def test_incomplete_or_mutated_release_cannot_open_heldout_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=root/'release.json'
            release={'status':'collection_precommitted','allowed_splits':['reference','validation','test'],
                     'observation':{'anchor':'injection_confirmed_at','pre_seconds':30,'post_seconds':30,'completed_spans_only':True},
                     'files_sha256':{}}
            path.write_text(json.dumps(release))
            with self.assertRaisesRegex(ValueError,'source pins'):verify_release(path,root,'test')


if __name__=='__main__':unittest.main()
