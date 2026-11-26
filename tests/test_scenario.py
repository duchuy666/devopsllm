import copy
import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import ExitStack
from itertools import count
from types import SimpleNamespace
from unittest.mock import patch,MagicMock
from experiments.scenario import render,memory_bytes
from app.experiment_runtime import health_issues
from scripts.run_scenario import validate_receipt
from scripts.run_scenario import execute_one


class ScenarioTests(unittest.TestCase):
    def setUp(self):
        root=Path(__file__).resolve().parents[1]
        self.rows=json.loads((root/'experiments/scenario-plan.json').read_text())['scenarios']
        self.deployments={}
        for name in ('front-end','catalogue','payment','user','carts','orders','shipping'):
            self.deployments[name]={'spec':{'template':{'spec':{'containers':[
                {'name':name,'resources':{'limits':{'memory':'200Mi'}}}]}}}}
        self.services={name:{'metadata':{'namespace':'sock-shop'},'spec':{'clusterIP':f'10.96.0.{i+2}'}}
                       for i,name in enumerate(self.deployments)}

    def test_all_planned_manifests_keep_namespace_and_directed_target(self):
        for row in self.rows:
            manifest,details=render(row,self.deployments,self.services,'prepared-'+row['scenario_id'].lower())
            self.assertEqual(manifest['metadata']['namespace'],'sock-shop')
            self.assertEqual(manifest['spec']['selector']['namespaces'],['sock-shop'])
            if row['variant'].startswith('network-'):
                self.assertEqual(details['source_service'],row['target'][0])
                self.assertEqual(details['destination_service'],row['target'][1])
                self.assertEqual(manifest['spec']['externalTargets'],[self.services[row['target'][1]]['spec']['clusterIP']])

    def test_memory_is_bytes_of_target_limit_not_percent_of_node(self):
        row=next(r for r in self.rows if r['variant']=='memory')
        manifest,details=render(row,self.deployments,self.services,'memory-check')
        size=manifest['spec']['stressors']['memory']['size']
        self.assertTrue(size.isdigit())
        self.assertEqual(int(size),int(row['parameters']['additional_memory_fraction_of_declared_limit']*200*1024**2))
        self.assertEqual(details['declared_memory_limit_bytes'],memory_bytes('200Mi'))
        bad=copy.deepcopy(row);bad['target']='kube-system'
        with self.assertRaises(ValueError):render(bad,self.deployments,self.services,'bad')
        bad=copy.deepcopy(row);bad['parameters']['additional_memory_fraction_of_declared_limit']=2
        with self.assertRaises(ValueError):render(bad,self.deployments,self.services,'bad')

    def test_health_gate_rejects_node_cgroup_without_headroom(self):
        pod={'metadata':{'name':'test'},'status':{'conditions':[{'type':'Ready','status':'True'}]}}
        state={'pods':[pod],'support_pods':[pod],'nodes':[{'status':{'conditions':[{'type':'Ready','status':'True'}]}}],
            'chaos':[],'node_cgroup':{'memory_current_bytes':99,'memory_max_bytes':100,'full_pressure':{'avg10':0}}}
        self.assertIn('node_cgroup_less_than_5_percent_working_set_headroom',health_issues(state))
        state['node_cgroup']['working_set_bytes']=65
        self.assertFalse(health_issues(state))
        state['node_cgroup']['full_pressure']['avg10']=10
        self.assertIn('node_memory_stall_above_5_percent',health_issues(state))

    def test_old_receipt_and_hierarchical_oom_counters_cannot_authorize_injection(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'result.json'
            result={'status':'passed_short_soak','requested_seconds':600,'manifest_sha256':'hash',
                    'health_gate_version':'cgroup-working-set-v1'}
            sample={'at':dt.datetime.now(dt.timezone.utc).isoformat(),
                    'node_cgroup':{'events_source':'memory.events','memory_max_bytes':100},'pods':{},'support_pods':{}}
            path.write_text(json.dumps(result));(path.parent/'samples.json').write_text(json.dumps([sample]))
            state={'node_cgroup':{'memory_max_bytes':100},'pods':[],'support_pods':[]}
            with self.assertRaisesRegex(ValueError,'local node OOM'):validate_receipt(path,state,'hash')
            sample['node_cgroup']['events_source']='memory.events.local'
            sample['at']=(dt.datetime.now(dt.timezone.utc)-dt.timedelta(hours=1)).isoformat()
            (path.parent/'samples.json').write_text(json.dumps([sample]))
            with self.assertRaisesRegex(ValueError,'15 minutes'):validate_receipt(path,state,'hash')

    def run_simulated_candidate(self,create_timeout=False,other_owner=False):
        row=next(r for r in self.rows if r['variant']=='cpu' and r['split']=='reference')
        pod={'metadata':{'namespace':'sock-shop','name':'payment','uid':'stable'},
             'status':{'conditions':[{'type':'Ready','status':'True'}],
                       'containerStatuses':[{'name':'payment','restartCount':0}]}}
        state={'pods':[pod],'support_pods':[],'nodes':[{'status':{'conditions':[{'type':'Ready','status':'True'}]}}],
               'chaos':[],'node_cgroup':{'memory_current_bytes':40,'memory_max_bytes':100,
                   'events':{'oom_kill':0},'full_pressure':{'avg10':0}}}
        support=copy.deepcopy(pod);support['metadata'].update(namespace='monitoring',name='collector')
        state['support_pods']=[support]
        calls=[];created={}
        def fake_kube(*args):
            calls.append(args)
            if args[0]=='create' and '--dry-run=server' not in args:
                import yaml
                created.update(yaml.safe_load(Path(args[-1]).read_text()))
                if create_timeout:raise RuntimeError('Transport timeout after create may have succeeded')
            if args[0]=='get':
                result=copy.deepcopy(created)
                if other_owner:result['metadata']['labels']['thesis.shyn/attempt']='another-owner'
                return json.dumps(result)
            return ''
        def fake_traffic(command,**kwargs):
            Path(command[command.index('--output')+1]).write_text(json.dumps({'completed_journeys':2,'failed_requests':0}))
            process=MagicMock();process.returncode=0;process.poll.return_value=0
            return process
        quality={'quality':{k:True for k in ('metrics_present','logs_present','traces_present')},'errors':{}}
        with tempfile.TemporaryDirectory() as tmp,ExitStack() as stack:
            root=Path(tmp);(root/'infra/sock-shop').mkdir(parents=True)
            (root/'infra/sock-shop/local-emulated.yaml').write_text('fixture')
            replacements={'ROOT':root,'inventory':lambda:(self.deployments,self.services),
                'snapshot':lambda:copy.deepcopy(state),'validate_receipt':lambda *a:None,
                'kube':fake_kube,'kube_json':lambda *a:{'status':{'conditions':[{'type':'AllInjected','status':'True'}]}},
                'capture':lambda *a:quality}
            for name,value in replacements.items():stack.enter_context(patch('scripts.run_scenario.'+name,value))
            stack.enter_context(patch('scripts.run_scenario.subprocess.Popen',side_effect=fake_traffic))
            stack.enter_context(patch('scripts.run_scenario.time.sleep'))
            stack.enter_context(patch('scripts.run_scenario.time.monotonic',side_effect=count(0,5)))
            stack.enter_context(patch('app.experiment_runtime.read_cgroup',return_value=state['node_cgroup']))
            stack.enter_context(patch('urllib.request.urlopen'))
            code=execute_one({},'plan-hash',row,SimpleNamespace(stability_result=root/'receipt.json'))
            record=json.loads(next((root/'data/candidates').glob('*/ground-truth.json')).read_text())
        return code,record,calls

    def test_completed_execution_still_requires_admission_review(self):
        code,record,calls=self.run_simulated_candidate()
        self.assertEqual(code,0)
        self.assertEqual(record['execution_status'],'captured_requires_review')
        self.assertEqual(record['admission_status'],'requires_review')
        self.assertEqual(record['dataset_role'],'development_candidate')

    def test_uncertain_create_response_still_cleans_owned_resource(self):
        code,record,calls=self.run_simulated_candidate(create_timeout=True)
        self.assertEqual(code,1)
        self.assertTrue(any(c[0]=='delete' for c in calls))
        self.assertIn('cleanup_completed_at',record)

    def test_cleanup_does_not_delete_another_owners_resource(self):
        code,record,calls=self.run_simulated_candidate(create_timeout=True,other_owner=True)
        self.assertEqual(code,1)
        self.assertFalse(any(c[0]=='delete' for c in calls))
        self.assertIn('ownership mismatch',record['cleanup_error'])
