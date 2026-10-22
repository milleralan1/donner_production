import unittest
from unittest.mock import Mock

from gcp_queue import publish_analysis_job


class PubSubQueueTests(unittest.TestCase):
    def test_publishes_the_job_id_and_waits_for_confirmation(self):
        publisher = Mock()
        publisher.publish.return_value.result.return_value = "message-1"

        result = publish_analysis_job(
            "projects/test-project/topics/alex-analysis-jobs",
            "job-123",
            publisher,
        )

        self.assertEqual(result, "message-1")
        publisher.publish.assert_called_once_with(
            "projects/test-project/topics/alex-analysis-jobs", job_id="job-123"
        )
        publisher.publish.return_value.result.assert_called_once_with(timeout=30)

    def test_rejects_non_resource_topic(self):
        with self.assertRaisesRegex(ValueError, "fully qualified"):
            publish_analysis_job("alex-analysis-jobs", "job-123", Mock())

    def test_rejects_missing_job_id(self):
        with self.assertRaisesRegex(ValueError, "job_id is required"):
            publish_analysis_job(
                "projects/test-project/topics/alex-analysis-jobs", "", Mock()
            )


if __name__ == "__main__":
    unittest.main()
