from collections import Counter
import unittest
from app.telemetry import query_logs


class LogExportTests(unittest.TestCase):
    def test_dense_window_preserves_entries_and_boundary_multiplicity(self):
        original=[[str(i),'line-'+str(i)] for i in range(10)]
        original.append(['3','line-3'])
        def get(url,params):
            rows=[r for r in original if params['start']<=int(r[0])<=params['end']]
            rows.sort(key=lambda r:int(r[0]))
            return {'status':'success','data':{'result':[{'stream':{'service':'example'},'values':rows[:params['limit']]}]}}
        result=query_logs(get,'http://local',0,9,page_limit=5)
        restored=result['data']['result'][0]['values']
        self.assertEqual(Counter(map(tuple,restored)),Counter(map(tuple,original)))
        self.assertFalse(result['export_metadata']['incomplete'])
        self.assertGreater(result['export_metadata']['query_count'],1)


if __name__=='__main__': unittest.main()
