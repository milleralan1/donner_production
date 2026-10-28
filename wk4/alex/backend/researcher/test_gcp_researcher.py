import unittest
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from gcp_tools import GCPIngestionClient
from gcp_server import ResearchConfigurationError, _get_runtime_config, app


class FakeResponse:
    def __init__(self, status_code=201, payload=None):
        self.status_code = status_code
        self.payload = payload or {"document_id": "doc-123"}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "request failed",
                request=httpx.Request("POST", "https://ingest.example/ingest"),
                response=httpx.Response(self.status_code),
            )

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, url, json, timeout):
        self.calls.append((url, json, timeout))
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class GCPIngestionClientTests(unittest.TestCase):
    def test_ingest_sends_tenant_and_metadata_to_private_service(self):
        session = FakeSession([FakeResponse()])
        client = GCPIngestionClient(
            endpoint="https://ingest-abc.run.app",
            tenant_id="public_research",
            session=session,
        )

        result = client.ingest("ETF trends", "Research notes")

        self.assertTrue(result["success"])
        self.assertEqual(result["document_id"], "doc-123")
        url, body, timeout = session.calls[0]
        self.assertEqual(url, "https://ingest-abc.run.app/ingest")
        self.assertEqual(body["tenant_id"], "public_research")
        self.assertEqual(body["metadata"], {"topic": "ETF trends"})
        self.assertEqual(timeout, 30)

    def test_ingest_retries_transient_server_errors_only(self):
        session = FakeSession(
            [FakeResponse(503), FakeResponse(201)]
        )
        client = GCPIngestionClient(
            endpoint="https://ingest-abc.run.app",
            session=session,
        )

        with patch("gcp_tools.wait_exponential", return_value=lambda _: 0):
            result = client.ingest("ETF trends", "Research notes")

        self.assertEqual(result["document_id"], "doc-123")
        self.assertEqual(len(session.calls), 2)

    def test_ingest_does_not_retry_client_errors(self):
        session = FakeSession([FakeResponse(403), FakeResponse(201)])
        client = GCPIngestionClient(
            endpoint="https://ingest-abc.run.app",
            session=session,
        )

        with self.assertRaises(httpx.HTTPStatusError):
            client.ingest("ETF trends", "Research notes")
        self.assertEqual(len(session.calls), 1)

    def test_ingest_retries_transport_errors(self):
        session = FakeSession(
            [
                httpx.ConnectError("temporary connection failure"),
                FakeResponse(201),
            ]
        )
        client = GCPIngestionClient(
            endpoint="https://ingest-abc.run.app",
            session=session,
        )

        with patch("gcp_tools.wait_exponential", return_value=lambda _: 0):
            result = client.ingest("ETF trends", "Research notes")
        self.assertEqual(result["document_id"], "doc-123")
        self.assertEqual(len(session.calls), 2)

    def test_endpoint_must_be_https_and_tenant_valid(self):
        with self.assertRaisesRegex(ValueError, "HTTPS"):
            GCPIngestionClient(endpoint="http://ingest.example")
        with self.assertRaisesRegex(ValueError, "RESEARCH_TENANT_ID"):
            GCPIngestionClient(
                endpoint="https://ingest.example",
                tenant_id="tenant/other",
                session=FakeSession([]),
            )


class GCPResearcherAPITests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_health_does_not_expose_aws_configuration(self):
        response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "healthy")
        self.assertNotIn("aws", response.text.lower())

    def test_research_requires_a_nonblank_topic_if_provided(self):
        response = self.client.post("/research", json={"topic": " "})
        self.assertEqual(response.status_code, 422)

    def test_research_route_returns_agent_result(self):
        async def fake_research(_topic):
            return "Brief market analysis"

        with patch("gcp_server.run_research_agent", side_effect=fake_research):
            response = self.client.post(
                "/research", json={"topic": "long-term bond ETFs"}
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"research": "Brief market analysis"})

    def test_research_errors_do_not_expose_provider_details(self):
        async def failing_research(_topic):
            raise RuntimeError("secret provider response")

        with self.assertLogs("gcp_server", level="ERROR"):
            with patch("gcp_server.run_research_agent", side_effect=failing_research):
                response = self.client.post("/research", json={})

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["detail"], "Research request failed")
        self.assertNotIn("secret provider response", response.text)

    def test_runtime_config_requires_huggingface_model_token_and_ingestion_url(self):
        with patch.dict(
            "os.environ",
            {
                "HF_TOKEN": "test-token",
                "ALEX_LLM_MODEL": "openai/gpt-oss-120b",
                "ALEX_INGESTION_URL": "https://ingest-abc.run.app",
            },
            clear=True,
        ):
            self.assertEqual(
                _get_runtime_config(),
                "openai/gpt-oss-120b",
            )

        with patch.dict(
            "os.environ",
            {
                "HF_TOKEN": "test-token",
                "ALEX_LLM_MODEL": "Qwen/Qwen3-4B-Thinking-2507",
                "ALEX_INGESTION_URL": "https://ingest-abc.run.app",
            },
            clear=True,
        ):
            self.assertEqual(
                _get_runtime_config(),
                "Qwen/Qwen3-4B-Thinking-2507",
            )

    def test_runtime_config_requires_huggingface_token(self):
        with patch.dict(
            "os.environ",
            {
                "ALEX_INGESTION_URL": "https://ingest-abc.run.app",
            },
            clear=True,
        ):
            with self.assertRaisesRegex(ResearchConfigurationError, "HF_TOKEN"):
                _get_runtime_config()


if __name__ == "__main__":
    unittest.main()
