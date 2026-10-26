import base64
import json
import os
import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from gcp_server import create_app


class GCPAgentServerTests(unittest.TestCase):
    def setUp(self):
        self.handler = Mock(
            return_value={"success": True}
        )
        self.client = TestClient(create_app(lambda: self.handler))
        self.environment = patch.dict(os.environ, {"ALEX_AGENT_ROLE": "planner"})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def test_health_reports_role(self):
        response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "healthy", "role": "planner"})

    def test_health_requires_a_configured_role(self):
        with patch.dict(os.environ, {"ALEX_AGENT_ROLE": ""}):
            response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 503)

    def test_invoke_validates_and_unwraps_handler_response(self):
        response = self.client.post("/invoke", json={"job_id": "job-123"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"success": True})
        self.handler.assert_called_once_with({"job_id": "job-123"})

    def test_invoke_rejects_missing_job_id(self):
        response = self.client.post("/invoke", json={})
        self.assertEqual(response.status_code, 422)
        self.handler.assert_not_called()

    def test_tagger_accepts_instrument_batch_without_job_id(self):
        with patch.dict(os.environ, {"ALEX_AGENT_ROLE": "tagger"}):
            response = self.client.post(
                "/invoke", json={"instruments": [{"symbol": "VTI"}]}
            )
        self.assertEqual(response.status_code, 200)
        self.handler.assert_called_once_with({"instruments": [{"symbol": "VTI"}]})

    def test_pubsub_decodes_job_and_acknowledges_only_success(self):
        message = base64.b64encode(json.dumps({"job_id": "job-456"}).encode()).decode()
        response = self.client.post(
            "/pubsub",
            json={"message": {"data": message, "messageId": "msg-1"}},
        )
        self.assertEqual(response.status_code, 204)
        self.handler.assert_called_once_with({"job_id": "job-456"})

    def test_pubsub_rejects_invalid_base64(self):
        response = self.client.post("/pubsub", json={"message": {"data": "%%%!"}})
        self.assertEqual(response.status_code, 400)
        self.handler.assert_not_called()

    def test_pubsub_route_is_hidden_from_non_planner_agents(self):
        with patch.dict(os.environ, {"ALEX_AGENT_ROLE": "reporter"}):
            response = self.client.post("/pubsub", json={})
        self.assertEqual(response.status_code, 404)
        self.handler.assert_not_called()

    def test_failed_agent_response_is_not_acknowledged_as_success(self):
        self.handler.side_effect = RuntimeError("agent failed")
        message = base64.b64encode(json.dumps({"job_id": "job-456"}).encode()).decode()
        response = self.client.post(
            "/pubsub", json={"message": {"data": message}}
        )
        self.assertEqual(response.status_code, 502)


if __name__ == "__main__":
    unittest.main()
