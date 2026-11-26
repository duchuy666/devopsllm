import copy
import json
from pathlib import Path
import tempfile
import unittest
from scripts.test_dataset import evaluate


class DatasetAuditTests(unittest.TestCase):
    def fixture(self,root):
        plan=json.loads((Path(__file__).resolve().parents[1]/'experiments/scenario-plan.json').read_text())
        (root/'experiments').mkdir();(root/'experiments/scenario-plan.json').write_text(json.dumps(plan))
        row=copy.deepcopy(plan['scenarios'][0]);key='CANDIDATE-fixture';path=root/'data/candidates'/key;path.mkdir(parents=True)
        ground={'scenario':row,'execution_status':'preflight_failed','admission_status':'requires_review'}
        entry={'candidate_id':key,'path':str(path.relative_to(root)),'scenario_id':row['scenario_id'],'split':row['split'],
               'execution_status':'preflight_failed','admission_status':'requires_review','effect_review_status':'not_verified'}
        (path/'ground-truth.json').write_text(json.dumps(ground))
        registry={'official_admitted':0,'attempts':[entry]};(root/'experiments/candidate-registry.json').write_text(json.dumps(registry))
        return path,ground,registry

    def test_failed_attempt_is_retained_but_cannot_be_counted_as_official(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path,ground,registry=self.fixture(root)
            result=evaluate(root);self.assertFalse(result['errors']);self.assertEqual(result['captured_cases'],0)
            ground['admission_status']=registry['attempts'][0]['admission_status']='admitted';registry['official_admitted']=1
            (path/'ground-truth.json').write_text(json.dumps(ground));(root/'experiments/candidate-registry.json').write_text(json.dumps(registry))
            self.assertTrue(any('cannot be officially admitted' in x for x in evaluate(root)['errors']))

    def test_registry_plan_mismatch_and_unregistered_attempts_fail_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path,ground,registry=self.fixture(root)
            ground['scenario']['seed']+=1;(path/'ground-truth.json').write_text(json.dumps(ground))
            (root/'data/candidates/CANDIDATE-unregistered').mkdir()
            result=evaluate(root)
            self.assertTrue(any('Plan mismatch' in x for x in result['errors']))
            self.assertTrue(any('Unregistered' in x for x in result['errors']))
