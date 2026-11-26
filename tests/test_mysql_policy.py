import copy
import unittest
from app.mysql_policy import apply_mysql_policy,CONFIG_PATH


class MysqlPolicyTests(unittest.TestCase):
    def fixture(self):
        return [{'kind':'Deployment','metadata':{'name':'catalogue-db','namespace':'sock-shop'},'spec':{'template':{'spec':{
            'containers':[{'name':'catalogue-db','image':'pinned-mysql','command':['original-entrypoint'],
                'args':['mysqld'],'env':[{'name':'MYSQL_ROOT_PASSWORD','valueFrom':{'secretKeyRef':{'name':'fixture','key':'password'}}}],
                'resources':{'limits':{'memory':'512Mi'}},'volumeMounts':[{'name':'existing','mountPath':'/var/lib/mysql'}]}],
            'volumes':[{'name':'existing','persistentVolumeClaim':{'claimName':'keep-data'}}]}}}}]

    def test_preserves_image_entrypoint_credentials_limits_and_data(self):
        rows=self.fixture();before=copy.deepcopy(rows);result=apply_mysql_policy(rows,'[mysqld]\nperformance_schema=OFF\n')
        self.assertEqual(rows,before);self.assertEqual(result,apply_mysql_policy(result,'[mysqld]\nperformance_schema=OFF\n'))
        old=before[0]['spec']['template']['spec'];new=result[0]['spec']['template']['spec']
        for name in ('image','command','args','env','resources'):self.assertEqual(old['containers'][0][name],new['containers'][0][name])
        self.assertEqual(old['volumes'][0],new['volumes'][0]);self.assertTrue(new['containers'][0]['volumeMounts'][-1]['readOnly'])

    def test_wrong_namespace_or_conflicting_config_mount_is_rejected(self):
        rows=self.fixture();rows[0]['metadata']['namespace']='other'
        with self.assertRaises(ValueError):apply_mysql_policy(rows,'fixture')
        rows=self.fixture();rows[0]['spec']['template']['spec']['containers'][0]['volumeMounts'].append({'name':'keep','mountPath':CONFIG_PATH})
        with self.assertRaises(ValueError):apply_mysql_policy(rows,'fixture')
