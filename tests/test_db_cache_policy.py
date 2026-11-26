import copy
import unittest
from app.db_cache_policy import apply_policy,TARGETS,NAME


class CachePolicyTests(unittest.TestCase):
    def fixture(self):
        return [{'kind':'Deployment','metadata':{'name':name,'namespace':'sock-shop'},'spec':{'template':{'spec':{
            'containers':[{'name':name,'image':'pinned-fixture','command':['original-entrypoint'],
                'args':['--keep-seed-data'],'volumeMounts':[{'name':'existing-data','mountPath':'/data'}]}],
            'volumes':[{'name':'existing-data','persistentVolumeClaim':{'claimName':'keep-data'}}]}}}} for name in TARGETS]

    def test_hook_preserves_entrypoint_data_volumes_and_is_idempotent(self):
        original=self.fixture();before=copy.deepcopy(original);result=apply_policy(original,'fixture script')
        self.assertEqual(original,before)
        self.assertEqual(result,apply_policy(result,'fixture script'))
        self.assertEqual(sum(r['kind']=='ConfigMap' for r in result),1)
        for row in result[:-1]:
            spec=row['spec']['template']['spec'];container=spec['containers'][0]
            self.assertEqual(container['command'],['original-entrypoint'])
            self.assertEqual(container['args'],['--keep-seed-data'])
            self.assertEqual(spec['volumes'][0]['persistentVolumeClaim']['claimName'],'keep-data')
            self.assertTrue(container['volumeMounts'][-1]['readOnly'])

    def test_wrong_namespace_or_existing_hook_is_rejected(self):
        rows=self.fixture();rows[0]['metadata']['namespace']='other'
        with self.assertRaises(ValueError):apply_policy(rows,'fixture')
        rows=self.fixture();rows[0]['spec']['template']['spec']['containers'][0]['lifecycle']={'postStart':{'exec':{'command':['keep-me']}}}
        with self.assertRaises(ValueError):apply_policy(rows,'fixture')
