import unittest
from unittest.mock import Mock

from src.models import Jobs


class JobClaimTests(unittest.TestCase):
    def test_claim_uses_single_conditional_update_and_returns_true_when_updated(self):
        client = Mock()
        client.query_one.return_value = {"id": "job-id"}
        jobs = Jobs(client)

        self.assertTrue(jobs.claim_for_processing("job-id"))

        sql, parameters = client.query_one.call_args.args
        self.assertIn("status IN ('pending', 'failed')", sql)
        self.assertIn("INTERVAL '65 minutes'", sql)
        self.assertIn("RETURNING id", sql)
        self.assertEqual(
            parameters,
            {"id": "job-id"},
        )

    def test_claim_returns_false_when_another_delivery_already_claimed_job(self):
        client = Mock()
        client.query_one.return_value = None
        jobs = Jobs(client)

        self.assertFalse(jobs.claim_for_processing("job-id"))


if __name__ == "__main__":
    unittest.main()
