import concurrent.futures
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from app.capture_jobs import run_serialized,persist_source


class CaptureJobTests(unittest.TestCase):
    def test_concurrent_alert_jobs_never_capture_at_same_time_and_keep_arguments(self):
        state={'active':0,'peak':0};lock=threading.Lock()
        def work(identity,cutoff):
            with lock:
                state['active']+=1;state['peak']=max(state['peak'],state['active'])
            time.sleep(.01)
            with lock:state['active']-=1
            return identity,cutoff
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            futures=[pool.submit(run_serialized,work,i,1234+i) for i in range(6)]
            self.assertEqual([f.result() for f in futures],[(i,1234+i) for i in range(6)])
        self.assertEqual(state['peak'],1)

    def test_streamed_persist_preserves_payload_and_returns_only_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload={'result':{'values':['x'*10000]},'export_metadata':{'incomplete':True,'queried_services':['orders']}}
            saved=persist_source(lambda _:payload,'jaeger',Path(tmp))
            self.assertEqual(json.loads((Path(tmp)/'jaeger.json').read_text()),payload)
            self.assertEqual(saved['status'],'partial');self.assertNotIn('result',saved)
            self.assertFalse((Path(tmp)/'jaeger.json.partial').exists())

    def test_serial_slot_is_released_after_failure(self):
        def broken():raise ValueError('capture failed')
        with self.assertRaises(ValueError):run_serialized(broken)
        self.assertEqual(run_serialized(lambda:'next job'),'next job')
