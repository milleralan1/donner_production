import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from vertex_embeddings import VertexEmbeddingClient


class FakeModels:
    def __init__(self, response):
        self.response = response
        self.call = None

    def embed_content(self, **kwargs):
        self.call = kwargs
        return self.response


class FakeClient:
    def __init__(self, response):
        self.models = FakeModels(response)


class VertexEmbeddingClientTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(
            os.environ,
            {
                "EMBEDDING_MODEL": "gemini-embedding-001",
                "GOOGLE_CLOUD_PROJECT": "alex-test",
                "GOOGLE_CLOUD_LOCATION": "global",
                "EMBEDDING_OUTPUT_DIMENSIONALITY": "3",
            },
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def test_embed_returns_values_and_sets_document_task_type(self):
        fake_client = FakeClient(
            SimpleNamespace(embeddings=[SimpleNamespace(values=[0.1, 0.2, 0.3])])
        )
        embedding_client = VertexEmbeddingClient(client=fake_client)

        result = embedding_client.embed("Company market analysis")

        self.assertEqual(result, [0.1, 0.2, 0.3])
        self.assertEqual(fake_client.models.call["model"], "gemini-embedding-001")
        self.assertEqual(
            fake_client.models.call["config"].task_type, "RETRIEVAL_DOCUMENT"
        )
        self.assertEqual(
            fake_client.models.call["config"].output_dimensionality, 3
        )

    def test_embed_supports_retrieval_query_task(self):
        fake_client = FakeClient(
            SimpleNamespace(embeddings=[SimpleNamespace(values=[0.1, 0.2, 0.3])])
        )
        embedding_client = VertexEmbeddingClient(client=fake_client)

        embedding_client.embed("market trends", task_type="RETRIEVAL_QUERY")

        self.assertEqual(
            fake_client.models.call["config"].task_type, "RETRIEVAL_QUERY"
        )

    def test_embed_rejects_empty_text(self):
        embedding_client = VertexEmbeddingClient(client=FakeClient(None))

        with self.assertRaisesRegex(ValueError, "non-empty"):
            embedding_client.embed(" ")

    def test_embed_rejects_wrong_dimension(self):
        fake_client = FakeClient(
            SimpleNamespace(embeddings=[SimpleNamespace(values=[0.1, 0.2])])
        )
        embedding_client = VertexEmbeddingClient(client=fake_client)

        with self.assertRaisesRegex(RuntimeError, "dimension mismatch"):
            embedding_client.embed("market trends")


if __name__ == "__main__":
    unittest.main()
