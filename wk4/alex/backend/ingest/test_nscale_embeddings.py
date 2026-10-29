import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from nscale_embeddings import NscaleEmbeddingClient


class FakeEmbeddings:
    def __init__(self, response):
        self.response = response
        self.call = None

    def create(self, **kwargs):
        self.call = kwargs
        return self.response


class FakeClient:
    def __init__(self, response):
        self.embeddings = FakeEmbeddings(response)


class NscaleEmbeddingClientTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(
            os.environ,
            {
                "EMBEDDING_MODEL": "Qwen/Qwen3-Embedding-8B",
                "NSCALE_API_KEY": "test-key",
                "NSCALE_BASE_URL": "https://inference.api.nscale.com/v1",
                "EMBEDDING_OUTPUT_DIMENSIONALITY": "3",
            },
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def test_embed_returns_values_and_uses_configured_model(self):
        fake_client = FakeClient(
            SimpleNamespace(data=[SimpleNamespace(embedding=[0.1, 0.2, 0.3])])
        )
        embedding_client = NscaleEmbeddingClient(client=fake_client)

        result = embedding_client.embed("Company market analysis")

        self.assertEqual(result, [0.1, 0.2, 0.3])
        self.assertEqual(
            fake_client.embeddings.call,
            {
                "model": "Qwen/Qwen3-Embedding-8B",
                "input": "Company market analysis",
                "dimensions": 3,
            },
        )

    def test_embed_accepts_query_task_type(self):
        fake_client = FakeClient(
            SimpleNamespace(data=[SimpleNamespace(embedding=[0.1, 0.2, 0.3])])
        )

        result = NscaleEmbeddingClient(client=fake_client).embed(
            "market trends", task_type="RETRIEVAL_QUERY"
        )

        self.assertEqual(result, [0.1, 0.2, 0.3])

    def test_embed_rejects_empty_text(self):
        embedding_client = NscaleEmbeddingClient(client=FakeClient(None))

        with self.assertRaisesRegex(ValueError, "non-empty"):
            embedding_client.embed(" ")

    def test_embed_rejects_wrong_dimension(self):
        fake_client = FakeClient(
            SimpleNamespace(data=[SimpleNamespace(embedding=[0.1, 0.2])])
        )

        with self.assertRaisesRegex(RuntimeError, "dimension mismatch"):
            NscaleEmbeddingClient(client=fake_client).embed("market trends")

    def test_requires_api_key(self):
        with patch.dict(
            os.environ,
            {"EMBEDDING_MODEL": "Qwen/Qwen3-Embedding-8B"},
            clear=True,
        ):
            with self.assertRaisesRegex(ValueError, "NSCALE_API_KEY"):
                NscaleEmbeddingClient(client=FakeClient(None))

    def test_configures_openai_client_for_nscale(self):
        with patch("openai.OpenAI") as client_factory:
            NscaleEmbeddingClient()

        client_factory.assert_called_once_with(
            api_key="test-key",
            base_url="https://inference.api.nscale.com/v1",
        )


if __name__ == "__main__":
    unittest.main()
