import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts.run_dataset_collection import inherit_cases
from experiments.audit_plan import audit


class CollectionInheritanceTests(unittest.TestCase):
    def fixture(self,root):
        release_dir=root/'release';release_dir.mkdir()
        pins={}
        for name,text in [('app/context_builder.py','same inference'),('scripts/run_dataset_collection.py','old scheduler')]:
            p=release_dir/'sources'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text)
            pins[name]=hashlib.sha256(p.read_bytes()).hexdigest()
        old={'observation':{'fixed':True},'provider':{'model':'fixture'},'prompt_fingerprint':{'v':'fixture'},'files_sha256':pins}
        path=release_dir/'release.json';path.write_text(json.dumps(old));digest=hashlib.sha256(path.read_bytes()).hexdigest()
        row={'scenario_id':'S0001','split':'reference','traffic_pause_seconds':1.5}
        candidate=root/'data/candidates/CANDIDATE-fixture';candidate.mkdir(parents=True)
        (candidate/'collection-release.json').write_bytes(path.read_bytes())
        (candidate/'ground-truth.json').write_text(json.dumps({'scenario':row,'collection_release_sha256':digest}))
        journal={'status':'superseded_before_heldout_collection','release':str(path),'release_sha256':digest,
                 'attempts':[{'scenario_id':'S0001','status':'captured_requires_review','candidate_paths':[str(candidate.relative_to(root))]}]}
        jp=root/'journal.json';jp.write_text(json.dumps(journal));new=copy.deepcopy(old)
        new['files_sha256']['scripts/run_dataset_collection.py']='new scheduler hash'
        return jp,new,row,candidate

    def test_unchanged_reference_capture_keeps_original_release_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);jp,new,row,case=self.fixture(root);before=(case/'ground-truth.json').read_bytes()
            with patch('scripts.run_dataset_collection.ROOT',root),patch('scripts.run_dataset_collection.review',return_value={'checks':{'passed':True}}):
                result=inherit_cases(jp,new,[row])
            self.assertEqual(len(result),1);self.assertIn('inherited_from_release_sha256',result[0])
            self.assertEqual(before,(case/'ground-truth.json').read_bytes())

    def test_changed_observation_or_inference_source_cannot_be_inherited(self):
        for kind in ('window','source'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);jp,new,row,_=self.fixture(root)
                if kind=='window':new['observation']={'different':True}
                else:new['files_sha256']['app/context_builder.py']='changed'
                with patch('scripts.run_dataset_collection.ROOT',root),self.assertRaises(ValueError):inherit_cases(jp,new,[row])

    def test_nested_inheritance_preserves_oldest_release_and_rejects_forged_origin(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);jp,new,row,case=self.fixture(root)
            journal=json.loads(jp.read_text());origin=journal['release_sha256']
            journal['attempts'][0]['inherited_from_release_sha256']=origin
            predecessor=json.loads(Path(journal['release']).read_text());predecessor['migration']='second release'
            Path(journal['release']).write_text(json.dumps(predecessor))
            journal['release_sha256']=hashlib.sha256(Path(journal['release']).read_bytes()).hexdigest();jp.write_text(json.dumps(journal))
            with patch('scripts.run_dataset_collection.ROOT',root),patch('scripts.run_dataset_collection.review',return_value={'checks':{'passed':True}}):
                result=inherit_cases(jp,new,[row]);self.assertEqual(result[0]['inherited_from_release_sha256'],origin)
                (case/'collection-release.json').write_text('{}')
                with self.assertRaisesRegex(ValueError,'Original candidate release'):inherit_cases(jp,new,[row])

    def test_changing_completed_setting_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);jp,new,row,_=self.fixture(root);row['traffic_pause_seconds']=2
            with patch('scripts.run_dataset_collection.ROOT',root),self.assertRaisesRegex(ValueError,'Completed setting changed'):
                inherit_cases(jp,new,[row])

    def test_seed_or_profile_label_changes_do_not_make_duplicate_setting_distinct(self):
        root=Path(__file__).resolve().parents[1];plan=json.loads((root/'experiments/scenario-plan.json').read_text())
        self.assertEqual(audit(plan)['distinct_nominal_settings'],200)
        duplicate=next(r for r in plan['scenarios'] if r['scenario_id']=='S0138')
        original=next(r for r in plan['scenarios'] if r['scenario_id']=='S0135')
        for key in ('parameters','duration_seconds','traffic_pause_seconds'):duplicate[key]=copy.deepcopy(original[key])
        duplicate['traffic_profile']='a new name';duplicate['seed']+=999
        self.assertTrue(any('Duplicate nominal settings' in e for e in audit(plan)['errors']))


if __name__=='__main__':unittest.main()
