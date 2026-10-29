import json
import unittest
from unittest.mock import Mock

from fastapi.testclient import TestClient

from gcp_ingestion import GCPIngestionService
from gcp_service import create_app


class FakeEmbeddingClient:
    def __init__(self):
        self.calls = []
        self.result = [0.1, 0.2, 0.3]

    def embed(self, text, task_type):
        self.calls.append((text, task_type))
        return self.result


class FakeDatabaseClient:
    def __init__(self):
        self.inserts = []
        self.queries = []
        self.query_rows = [{"id": "document-123"}]
        self.insert_result = "document-123"

    def insert(self, table, data, returning):
        self.inserts.append((table, data, returning))
        return self.insert_result

    def query(self, sql, parameters):
        self.queries.append((sql, parameters))
        return self.query_rows


class FakeDatabase:
    def __init__(self):
        self.client = FakeDatabaseClient()


class GCPIngestionServiceTests(unittest.TestCase):
    def setUp(self):
        self.embedding = FakeEmbeddingClient()
        self.database = FakeDatabase()
        self.service = GCPIngestionService(
            embedding_client=self.embedding,
            database=self.database,
            embedding_dimension=3,
        )

    def test_ingest_stores_document_and_embedding_in_pgvector_table(self):
        document_id = self.service.ingest(
            "Market update", "tenant_1", {"ticker": "ABC"}
        )

        self.assertEqual(document_id, "document-123")
        sql, parameters = self.database.client.queries[0]
        self.assertIn("INSERT INTO research_documents", sql)
        self.assertIn("CAST(:metadata AS jsonb)", sql)
        self.assertIn("CAST(:embedding AS vector)", sql)
        self.assertEqual(parameters["tenant_id"], "tenant_1")
        self.assertEqual(parameters["content"], "Market update")
        self.assertEqual(json.loads(parameters["metadata"]), {"ticker": "ABC"})
        self.assertEqual(json.loads(parameters["embedding"]), [0.1, 0.2, 0.3])
        self.assertEqual(self.embedding.calls[0][1], "RETRIEVAL_DOCUMENT")

    def test_search_runs_cosine_query_scoped_to_tenant(self):
        self.database.client.query_rows = [
            {
                "id": "document-123",
                "content": "Market update",
                "metadata": {"ticker": "ABC"},
                "distance": 0.2,
            }
        ]

        matches = self.service.search("market update", "tenant_1")

        self.assertEqual(
            matches,
            [
                {
                    "id": "document-123",
                    "distance": 0.2,
                    "text": "Market update",
                    "metadata": {"ticker": "ABC"},
                }
            ],
        )
        self.assertEqual(self.embedding.calls[-1][1], "RETRIEVAL_QUERY")
        sql, parameters = self.database.client.queries[-1]
        self.assertIn("embedding <=> CAST(:embedding AS vector)", sql)
        self.assertIn("WHERE tenant_id = :tenant_id", sql)
        self.assertEqual(parameters["tenant_id"], "tenant_1")
        self.assertEqual(json.loads(parameters["embedding"]), [0.1, 0.2, 0.3])
        self.assertEqual(parameters["limit"], 5)

    def test_search_decodes_json_metadata_and_drops_invalid_distances(self):
        self.database.client.query_rows = [
            {
                "id": "document-123",
                "content": "Market update",
                "metadata": '{"ticker":"ABC"}',
                "distance": 0.2,
            },
            {
                "id": "invalid",
                "content": "Invalid result",
                "metadata": "{}",
                "distance": float("nan"),
            },
        ]

        matches = self.service.search("market update", "tenant_1")

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["metadata"], {"ticker": "ABC"})

    def test_ingest_rejects_embedding_dimension_mismatch(self):
        self.embedding.result = [0.1, 0.2]

        with self.assertRaisesRegex(ValueError, "dimension mismatch"):
            self.service.ingest("Market update", "tenant_1")
        self.assertEqual(self.database.client.inserts, [])

    def test_search_rejects_embedding_dimension_mismatch(self):
        self.embedding.result = [0.1, 0.2]

        with self.assertRaisesRegex(ValueError, "dimension mismatch"):
            self.service.search("Market update", "tenant_1")
        self.assertEqual(self.database.client.queries, [])

    def test_ingest_rejects_non_json_metadata(self):
        with self.assertRaisesRegex(ValueError, "valid JSON"):
            self.service.ingest(
                "Market update", "tenant_1", {"invalid": float("nan")}
            )
        self.assertEqual(self.database.client.inserts, [])

    def test_ingest_rejects_invalid_tenant_and_blank_text(self):
        with self.assertRaisesRegex(ValueError, "tenant_id"):
            self.service.ingest("Market update", "tenant with spaces")
        with self.assertRaisesRegex(ValueError, "non-empty"):
            self.service.ingest(" ", "tenant_1")
        self.assertEqual(self.database.client.inserts, [])

    def test_search_rejects_invalid_limit(self):
        with self.assertRaisesRegex(ValueError, "limit"):
            self.service.search("query", "tenant_1", limit=101)
        self.assertEqual(self.database.client.queries, [])

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
