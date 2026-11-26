import unittest
from app.costs import estimate_generation


class CostTests(unittest.TestCase):
    def test_recorded_pilot_usage_paid_equivalent(self):
        actual=estimate_generation('gemini-3.8-flash',{'prompt_token_count':14146,'candidates_token_count':612,
                                                     'total_token_count':14758},'2026-11-20T14:04:12+00:00')
        self.assertAlmostEqual(actual['estimated_paid_api_cost_usd'],0.0129045)
        self.assertFalse(actual['billing_verified'])
        self.assertFalse(actual['embedding_and_index_cost_included'])

    def test_expired_price_is_not_used(self):
        actual=estimate_generation('gemini-3.8-flash',{'prompt_token_count':100},'2027-01-01T00:00:00+00:00')
        self.assertIsNone(actual['estimated_paid_api_cost_usd'])


if __name__=='__main__':unittest.main()
