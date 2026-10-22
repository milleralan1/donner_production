import os
import unittest
from unittest.mock import Mock, patch

with patch.dict(os.environ, {"ALEX_LLM_PROVIDER": "groq"}):
    from agent import invoke_cloud_run_agent


class CloudRunAgentInvocationTests(unittest.TestCase):
    @patch("google.auth.transport.requests.AuthorizedSession")
    @patch("google.oauth2.id_token.fetch_id_token_credentials")
    def test_invokes_private_service_with_id_token(
        self, fetch_credentials, authorized_session
    ):
        credentials = Mock()
        fetch_credentials.return_value = credentials
        response = Mock()
        response.json.return_value = {"success": True}
        session = authorized_session.return_value
        session.post.return_value = response
        payload = {"job_id": "job-123"}

        with patch.dict(
            os.environ,
            {
                "REPORTER_SERVICE_URL": "https://reporter-abc.run.app/",
                "REPORTER_SERVICE_AUDIENCE": "https://reporter-abc.run.app",
            },
        ):
            result = invoke_cloud_run_agent("Reporter", payload)

        self.assertEqual(result, {"success": True})
        fetch_credentials.assert_called_once()
        self.assertEqual(fetch_credentials.call_args.args[0], "https://reporter-abc.run.app")
        authorized_session.assert_called_once_with(credentials)
        session.post.assert_called_once_with(
            "https://reporter-abc.run.app/invoke",
            json=payload,
            timeout=600,
        )
        response.raise_for_status.assert_called_once()

    def test_rejects_non_https_service_url(self):
        with patch.dict(os.environ, {"TAGGER_SERVICE_URL": "http://localhost:8080"}):
            with self.assertRaisesRegex(ValueError, "HTTPS URL"):
                invoke_cloud_run_agent("Tagger", {"instruments": []})

    @patch("google.auth.transport.requests.AuthorizedSession")
    @patch("google.oauth2.id_token.fetch_id_token_credentials")
    def test_propagates_service_http_errors(
        self, fetch_credentials, authorized_session
    ):
        response = Mock()
        response.raise_for_status.side_effect = RuntimeError("service unavailable")
        authorized_session.return_value.post.return_value = response

        with patch.dict(
            os.environ, {"CHARTER_SERVICE_URL": "https://charter-abc.run.app"}
        ):
            with self.assertRaisesRegex(RuntimeError, "service unavailable"):
                invoke_cloud_run_agent("Charter", {"job_id": "job-123"})


if __name__ == "__main__":
    unittest.main()
