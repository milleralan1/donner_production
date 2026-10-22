import json
import unittest
from unittest.mock import Mock

from fastapi.testclient import TestClient

from gcp_ingestion import GCPIngestionService
from gcp_service import create_app


class FakeBlob:
    def __init__(self, name, bucket):
        self.name = name
        self.bucket = bucket
        self.payload = None
        self.deleted = False

    def upload_from_string(self, data, content_type):
        self.payload = data
        self.bucket.documents[self.name] = data
        self.content_type = content_type

    def delete(self):
        self.deleted = True
        self.bucket.documents.pop(self.name, None)

    def exists(self):
        return self.name in self.bucket.documents

    def download_as_text(self):
        return self.bucket.documents[self.name]


class FakeBucket:
    def __init__(self):
        self.documents = {}

    def blob(self, name):
        return FakeBlob(name, self)


class FakeStorage:
    def __init__(self):
        self.test_bucket = FakeBucket()

    def bucket(self, name):
        return self.test_bucket


class FakeEmbeddingClient:
    def __init__(self):
        self.calls = []

    def embed(self, text, task_type):
        self.calls.append((text, task_type))
        return [0.1, 0.2, 0.3]


class FakeResponse:
    status_code = 200

    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


class FakeAuthorizedSession:
    def __init__(self):
        self.calls = []
        self.response = FakeResponse({})

    def post(self, url, json, timeout):
        self.calls.append((url, json, timeout))
        return self.response


class GCPIngestionServiceTests(unittest.TestCase):
    def setUp(self):
        self.embedding = FakeEmbeddingClient()
        self.storage = FakeStorage()
        self.session = FakeAuthorizedSession()
        self.service = GCPIngestionService(
            embedding_client=self.embedding,
            storage_client=self.storage,
            authorized_session=self.session,
            project="alex-project",
            region="us-central1",
            embedding_dimension=3,
            bucket_name="alex-documents",
            index_id="index-123",
            index_endpoint_id="endpoint-123",
            deployed_index_id="deployed-123",
            public_endpoint_domain="123.us-central1-456.vdb.vertexai.goog",
        )

    def test_ingest_persists_source_and_upserts_tenant_restricted_vector(self):
        document_id = self.service.ingest(
            "Market update", "tenant_1", {"ticker": "ABC"}
        )

        object_key = f"tenant_1/{document_id}.json"
        source = json.loads(self.storage.test_bucket.documents[object_key])
        self.assertEqual(source["text"], "Market update")
        self.assertEqual(source["metadata"], {"ticker": "ABC"})
        self.assertEqual(self.embedding.calls[0][1], "RETRIEVAL_DOCUMENT")

        url, request, timeout = self.session.calls[0]
        self.assertTrue(url.endswith("/indexes/index-123:upsertDatapoints"))
        datapoint = request["datapoints"][0]
        self.assertEqual(datapoint["datapointId"], document_id)
        self.assertEqual(datapoint["restricts"][0]["allowList"], ["tenant_1"])
        self.assertEqual(timeout, 30)

    def test_search_filters_by_tenant_and_loads_document_from_storage(self):
        document_id = self.service.ingest("Market update", "tenant_1")
        self.session.response = FakeResponse(
            {
                "nearestNeighbors": [
                    {
                        "neighbors": [
                            {
                                "datapoint": {"datapointId": document_id},
                                "distance": 0.2,
                            }
                        ]
                    }
                ]
            }
        )

        matches = self.service.search("market update", "tenant_1")

        self.assertEqual(matches[0]["id"], document_id)
        self.assertEqual(matches[0]["text"], "Market update")
        self.assertEqual(self.embedding.calls[-1][1], "RETRIEVAL_QUERY")
        _, request, _ = self.session.calls[-1]
        query = request["queries"][0]
        self.assertEqual(query["datapoint"]["restricts"][0]["allowList"], ["tenant_1"])
        self.assertEqual(query["neighborCount"], 5)

    def test_search_drops_missing_documents_and_rejects_invalid_limit(self):
        self.session.response = FakeResponse(
            {"nearestNeighbors": [{"neighbors": [
                {"datapoint": {"datapointId": "not-stored"}, "distance": 0.3}
            ]}]}
        )
        self.assertEqual(self.service.search("query", "tenant_1"), [])

        with self.assertRaisesRegex(ValueError, "limit"):
            self.service.search("query", "tenant_1", limit=101)

    def test_search_does_not_return_another_tenants_document(self):
        self.service.ingest("Private market update", "tenant_2")
        document_id = next(
            name.split("/")[-1].removesuffix(".json")
            for name in self.storage.test_bucket.documents
        )
        self.session.response = FakeResponse(
            {"nearestNeighbors": [{"neighbors": [
                {"datapoint": {"datapointId": document_id}, "distance": 0.3}
            ]}]}
        )

        self.assertEqual(self.service.search("query", "tenant_1"), [])

    def test_failed_vector_upsert_removes_uploaded_document(self):
        self.session.response = FakeResponse({})
        self.session.response.status_code = 500

        with self.assertRaisesRegex(RuntimeError, "HTTP 500"):
            self.service.ingest("Market update", "tenant_1")
        self.assertEqual(self.storage.test_bucket.documents, {})

    def test_ingest_rejects_embedding_dimension_mismatch(self):
        self.embedding.embed = Mock(return_value=[0.1, 0.2])

        with self.assertRaisesRegex(ValueError, "dimension mismatch"):
            self.service.ingest("Market update", "tenant_1")
        self.assertEqual(self.session.calls, [])
        self.assertEqual(self.storage.test_bucket.documents, {})

    def test_ingest_rejects_non_json_metadata(self):
        with self.assertRaisesRegex(ValueError, "valid JSON"):
            self.service.ingest(
                "Market update", "tenant_1", {"invalid": float("nan")}
            )

    def test_search_rejects_non_vertex_endpoint_domain(self):
        self.service.public_endpoint_domain = "https://example.com"
        with self.assertRaisesRegex(ValueError, "Vertex AI Vector Search"):
            self.service._search_url()

    def test_service_health_and_ingest_routes(self):
        service = Mock()
        service.ingest.return_value = "document-123"
        client = TestClient(create_app(service))

        self.assertEqual(client.get("/healthz").json(), {"status": "ok"})
        response = client.post(
            "/ingest",
            json={"text": "Market update", "tenant_id": "tenant_1"},
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json(), {"document_id": "document-123"})

    def test_service_rejects_blank_tenant(self):
        client = TestClient(create_app(Mock()))
        response = client.post(
            "/ingest",
            json={"text": "Market update", "tenant_id": " "},
        )
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
