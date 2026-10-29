"""Construct an embedding client for the selected provider."""

import os


def create_embedding_client():
    """Create the configured embedding client; Vertex AI remains the default."""
    provider = os.environ.get("EMBEDDING_PROVIDER", "vertex_ai").lower()
    if provider == "vertex_ai":
        from vertex_embeddings import VertexEmbeddingClient

        return VertexEmbeddingClient()
    if provider == "nscale":
        from nscale_embeddings import NscaleEmbeddingClient

        return NscaleEmbeddingClient()
    raise ValueError(
        f"Unsupported EMBEDDING_PROVIDER {provider!r}; use 'vertex_ai' or 'nscale'"
    )
