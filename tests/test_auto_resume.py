import json
from pathlib import Path
import tempfile
import unittest
from scripts.auto_resume_collection import benign


class AutoResumeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.write('prev',{'scenario':{'variant':'memory','scenario_id':'S1'},'resolved':{'source_service':'shipping'},
                           'injection_requested_at':'2026-11-26T03:47:58+00:00','cleanup_completed_at':'2026-11-26T03:48:31+00:00'})
        self.write('last',{'error':'Pod identity/restarts changed since soak'})
        self.journal={'status':'stopped_requires_review','attempts':[
            {'status':'captured_requires_review','candidate_paths':['prev']},{'status':'preflight_failed','candidate_paths':['last']}]}

    def tearDown(self):self.tmp.cleanup()
    def write(self,name,ground):(self.root/name).mkdir();(self.root/name/'ground-truth.json').write_text(json.dumps(ground))

    def pods(self,name='shipping',reason='OOMKilled',finished='2026-11-26T03:47:59Z',created='2026-11-20T00:00:00Z',ready=True):
        return {'items':[{'metadata':{'name':name+'-x','labels':{'name':name},'creationTimestamp':created},
                          'status':{'containerStatuses':[{'ready':ready,'lastState':{'terminated':{'reason':reason,'finishedAt':finished}}}]}}]}

    def test_only_oom_of_previous_memory_target_is_benign(self):
        self.assertTrue(benign(self.journal,self.root,self.pods(),[])[0])
        for pods in (self.pods(name='orders'),self.pods(reason='Error'),self.pods(finished='2026-11-26T03:55:00Z'),
                     self.pods(created='2026-11-26T03:50:00Z'),self.pods(ready=False)):
            with self.subTest(pods=pods):self.assertFalse(benign(self.journal,self.root,pods,[])[0])
        self.assertFalse(benign(self.journal,self.root,self.pods(),[{'kind':'StressChaos'}])[0])

    def test_other_stop_reasons_wait_for_a_human(self):
        self.write('other',{'error':'Fresh soak failed'})
        journal={**self.journal,'attempts':[self.journal['attempts'][0],{'status':'preflight_failed','candidate_paths':['other']}]}
        self.assertFalse(benign(journal,self.root,self.pods(),[])[0])
        self.assertFalse(benign({**self.journal,'status':'running'},self.root,self.pods(),[])[0])


if __name__=='__main__':unittest.main()
