from contextlib import ExitStack,nullcontext
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import deploy_mysql_policy as deploy


class MysqlCutoverSafetyTests(unittest.TestCase):
    def simulate(self,phase):
        with tempfile.TemporaryDirectory() as tmp,ExitStack() as stack:
            root=Path(tmp);config=root/'infra/sock-shop/mysql-memory.cnf';config.parent.mkdir(parents=True);config.write_text('[mysqld]\nperformance_schema=OFF\n')
            proof=root/'proof.json';proof.write_text(json.dumps({'status':'isolated_mysql_restore_and_config_verified',
                'startup_tcp_readiness_verified':True,'config_sha256':hashlib.sha256(config.read_bytes()).hexdigest(),
                'source_image':'pinned','version':'5.7.17'}))
            source={'apiVersion':'apps/v1','kind':'Deployment','metadata':{'name':'catalogue-db','namespace':'sock-shop'},
                'spec':{'replicas':1,'template':{'spec':{'containers':[{'name':'catalogue-db','image':'pinned'}]}}}}
            calls=[]
            def read(ns,*args):
                if args[1]=='pods':return {'items':[]}
                return source if args[-1]=='catalogue-db' else {'spec':{'replicas':1}}
            def kube(args,payload=None):
                calls.append(args)
                if phase=='apply-timeout' and args[0]=='apply' and '--dry-run=server' not in args:raise RuntimeError('uncertain apply fixture')
            def backup(path):
                if phase=='backup':raise RuntimeError('backup failed fixture')
                path.write_bytes(b'fixture-backup');return hashlib.sha256(path.read_bytes()).hexdigest()
            def restore(*args):raise RuntimeError('restore failed fixture')
            for name,value in {'ROOT':root,'experiment_lock':nullcontext,'snapshot':lambda:{},'health_issues':lambda x:[],
                'kube_json':read,'kube':kube}.items():stack.enter_context(patch.object(deploy,name,value))
            for name,value in {'sql':lambda *a:'5.7.17','inventory':lambda *a:{'tables':['fixture']},
                'variables':lambda *a:dict(deploy.db.EXPECTED),'backup':backup,'restore':restore}.items():
                stack.enter_context(patch.object(deploy.db,name,value))
            stack.enter_context(patch('sys.argv',['script','--verification',str(proof)]))
            with self.assertRaises(RuntimeError):deploy.main()
            result=json.loads(next((root/'results/mysql-cutover').glob('*/result.json')).read_text())
            return calls,result

    def test_backup_failure_does_not_roll_database_and_resumes_writers(self):
        calls,result=self.simulate('backup')
        self.assertFalse(result['database_rollout_requested'])
        self.assertEqual(sum('--replicas=1' in x for x in calls),2)
        self.assertFalse(any(x[0]=='apply' and '--dry-run=server' not in x for x in calls))

    def test_restore_failure_keeps_writers_quiesced(self):
        calls,result=self.simulate('restore')
        self.assertTrue(result['writers_kept_quiesced_for_recovery'])
        self.assertFalse(any('--replicas=1' in x for x in calls))
        self.assertFalse(result['data_restored'])

    def test_uncertain_apply_does_not_resume_writers(self):
        calls,result=self.simulate('apply-timeout')
        self.assertTrue(result['database_rollout_requested'])
        self.assertTrue(result['writers_kept_quiesced_for_recovery'])
        self.assertFalse(any('--replicas=1' in x for x in calls))
