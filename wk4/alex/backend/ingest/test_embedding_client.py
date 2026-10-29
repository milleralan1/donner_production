import os
import unittest
from unittest.mock import patch

from embedding_client import create_embedding_client


class EmbeddingClientFactoryTests(unittest.TestCase):
    def test_defaults_to_vertex_ai(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("vertex_embeddings.VertexEmbeddingClient") as client_factory,
        ):
            client = create_embedding_client()

        self.assertIs(client, client_factory.return_value)

    def test_selects_nscale(self):
        with (
            patch.dict(os.environ, {"EMBEDDING_PROVIDER": "nscale"}, clear=True),
            patch("nscale_embeddings.NscaleEmbeddingClient") as client_factory,
        ):
            client = create_embedding_client()

        self.assertIs(client, client_factory.return_value)

    def test_rejects_unsupported_provider(self):
        with patch.dict(
            os.environ, {"EMBEDDING_PROVIDER": "unknown"}, clear=True
        ):
            with self.assertRaisesRegex(ValueError, "Unsupported EMBEDDING_PROVIDER"):
                create_embedding_client()


if __name__ == "__main__":
    unittest.main()
