import copy
import unittest
from app.frontend_tracing_policy import apply_frontend_tracing,COMMAND


class FrontendPolicyTests(unittest.TestCase):
    def fixture(self):
        return [{'kind':'Deployment','metadata':{'name':'front-end','namespace':'sock-shop'},'spec':{'template':{'spec':{
            'containers':[{'name':'front-end','image':'pinned-image','resources':{'limits':{'memory':'1000Mi'}},
                'securityContext':{'runAsNonRoot':True},'env':[{'name':'SESSION_REDIS','value':'true'}]}]}}}}]

    def test_image_limits_security_and_session_env_are_preserved(self):
        rows=self.fixture();before=copy.deepcopy(rows);result=apply_frontend_tracing(rows,'fixture')
        self.assertEqual(rows,before);self.assertEqual(result,apply_frontend_tracing(result,'fixture'))
        container=result[0]['spec']['template']['spec']['containers'][0]
        for key in ('image','resources','securityContext'):self.assertEqual(container[key],before[0]['spec']['template']['spec']['containers'][0][key])
        self.assertEqual(container['command'],COMMAND);self.assertEqual(container['env'][0]['name'],'SESSION_REDIS')

    def test_custom_entrypoint_or_wrong_namespace_is_rejected(self):
        rows=self.fixture();rows[0]['metadata']['namespace']='other'
        with self.assertRaises(ValueError):apply_frontend_tracing(rows,'fixture')
        rows=self.fixture();rows[0]['spec']['template']['spec']['containers'][0]['command']=['custom-app']
        with self.assertRaises(ValueError):apply_frontend_tracing(rows,'fixture')
