#!/usr/bin/env python3
"""Make one Nscale embedding request and print only its output dimension."""

from nscale_embeddings import NscaleEmbeddingClient


def main():
    embedding = NscaleEmbeddingClient().embed(
        "A representative financial market summary.",
        task_type="RETRIEVAL_DOCUMENT",
    )
    print(f"Nscale embedding succeeded with dimension {len(embedding)}")


if __name__ == "__main__":
    main()
