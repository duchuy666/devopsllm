import unittest
from app.live_context import prepare_live


class LiveContextBoundaryTests(unittest.TestCase):
    def test_path_traversal_and_external_urls_are_rejected_before_io(self):
        for value in ('../../.env','http://example.com','INC-../../secret',''):
            with self.subTest(value=value),self.assertRaises(ValueError):prepare_live(value)


if __name__=='__main__':unittest.main()
