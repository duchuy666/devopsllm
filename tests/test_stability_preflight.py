from contextlib import ExitStack
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch,MagicMock
from scripts import check_stability


class StabilityPreflightTests(unittest.TestCase):
    def simulate(self,response=None):
        with tempfile.TemporaryDirectory() as tmp,ExitStack() as stack:
            root=Path(tmp);manifest=root/'infra/sock-shop/local-emulated.yaml';manifest.parent.mkdir(parents=True);manifest.write_text('fixture')
            stack.enter_context(patch.object(check_stability,'ROOT',root))
            stack.enter_context(patch.object(check_stability.os,'chdir'))
            stack.enter_context(patch('sys.argv',['script','--seconds','60']))
            opener=stack.enter_context(patch.object(check_stability.urllib.request,'urlopen'))
            if response is None:opener.side_effect=OSError('fixture disconnected tunnel')
            else:opener.return_value.__enter__.return_value.status=response
            traffic=stack.enter_context(patch.object(check_stability.subprocess,'Popen'))
            cluster=stack.enter_context(patch.object(check_stability.subprocess,'run'))
            code=check_stability.main()
            self.assertEqual(code,1);traffic.assert_not_called();cluster.assert_not_called()
            result=json.loads(next((root/'results/stability').glob('*/result.json')).read_text())
            self.assertTrue(any('tunnel unavailable' in x.get('message','') for x in result['issues']))
            return result

    def test_disconnected_tunnel_never_starts_soak_traffic(self):self.simulate()
    def test_unhealthy_http_never_starts_soak_traffic(self):self.simulate(503)
