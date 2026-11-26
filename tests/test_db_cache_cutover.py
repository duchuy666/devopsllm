from contextlib import ExitStack,nullcontext
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from scripts import deploy_db_cache_policy as deploy


class CutoverSafetyTests(unittest.TestCase):
    def simulate(self,phase):
        with tempfile.TemporaryDirectory() as tmp,ExitStack() as stack:
            root=Path(tmp);packet=root/'packet';packet.mkdir();manifest=root/'infra/sock-shop/local-emulated.yaml'
            manifest.parent.mkdir(parents=True);manifest.write_text('old-manifest')
            (packet/'database-only.yaml').write_text('fixture')
            (packet/'execution-plan.json').write_text(json.dumps({'source_manifest_sha256':hashlib.sha256(manifest.read_bytes()).hexdigest(),
                'files_sha256':{'database-only.yaml':hashlib.sha256(b'fixture').hexdigest()}}))
            verification=root/'verification.json';verification.write_text(json.dumps({'status':'all_three_online_backups_restore_verified',
                'targets':[{'service':n,'source_image':'pinned-image'} for n in deploy.TARGETS]}))
            calls=[]
            def kube(ns,*args):
                if args[1]=='pods':return {'items':[]}
                return {'spec':{'replicas':1,'template':{'spec':{'containers':[{'image':'pinned-image'}]}}}}
            def execute(args,**kwargs):
                calls.append(args)
                if phase=='restore' and 'mongorestore' in args:raise RuntimeError('restore failed fixture')
                return SimpleNamespace(stdout=b'134217728\n',stderr=b'')
            def run(args,**kwargs):
                if 'mongodump' in args:
                    if phase=='backup':raise RuntimeError('backup failed fixture')
                    kwargs['stdout'].write(b'fixture-backup')
                return SimpleNamespace(returncode=0)
            for name,value in {'ROOT':root,'experiment_lock':nullcontext,'snapshot':lambda:{},'health_issues':lambda s:[],
                'kube_json':kube,'inventory':lambda resource:[{'collection':'fixture','documents':2}],
                'execute':execute}.items():stack.enter_context(patch.object(deploy,name,value))
            stack.enter_context(patch.object(deploy.subprocess,'run',side_effect=run))
            stack.enter_context(patch('sys.argv',['script','--packet',str(packet),'--restore-verification',str(verification)]))
            with self.assertRaises(RuntimeError):deploy.main()
            result=json.loads(next((root/'results/db-cache-cutover').glob('*/result.json')).read_text())
            return calls,result

    def test_failed_backup_resumes_writers_without_database_rollout(self):
        calls,result=self.simulate('backup')
        self.assertFalse(result['database_rollout_requested'])
        self.assertEqual(sum('--replicas=1' in row for row in calls),5)
        self.assertFalse(any('apply' in row and '--dry-run=server' not in row for row in calls))

    def test_failed_restore_keeps_writers_quiesced_and_backups_recorded(self):
        calls,result=self.simulate('restore')
        self.assertTrue(result['writers_kept_quiesced_for_data_recovery'])
        self.assertTrue(result['database_rollout_requested'])
        self.assertFalse(result['all_data_restored'])
        self.assertFalse(any('--replicas=1' in row for row in calls))
        self.assertEqual(len(result['targets']),3)
