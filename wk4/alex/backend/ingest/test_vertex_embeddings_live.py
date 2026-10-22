#!/usr/bin/env python3
"""Make one billable Vertex AI embedding request to verify model access."""

from vertex_embeddings import VertexEmbeddingClient


def main():
    client = VertexEmbeddingClient()
    embedding = client.embed(
        "A representative financial market summary.",
        task_type="RETRIEVAL_DOCUMENT",
    )
    print(f"Vertex AI embedding succeeded with dimension {len(embedding)}")


if __name__ == "__main__":
    main()
