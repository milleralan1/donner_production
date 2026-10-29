#!/usr/bin/env python3
"""Seed isolated pgvector smoke-test documents."""

import hashlib
import json
import math
import os
import sys
import uuid

from dotenv import load_dotenv

from src.models import Database

SEED_TENANT_ID = "alex-pgvector-seed"
SEED_SOURCE = "alex-pgvector-seed"
SEED_DOCUMENTS = (
    {
        "seed_id": "diversification",
        "content": (
            "Diversification spreads investments across asset classes and regions "
            "to reduce reliance on any single market."
        ),
    },
    {
        "seed_id": "retirement-bonds",
        "content": (
            "A bond allocation can provide income and may reduce portfolio "
            "volatility near retirement."
        ),
    },
    {
        "seed_id": "index-funds",
        "content": (
            "Broad-market index funds offer exposure to many companies through "
            "a single investment."
        ),
    },
)
_MAX_VECTOR_DIMENSIONS = 16_000


def build_seed_embedding(seed_id: str, dimension: int) -> list[float]:
    """Build a reproducible non-zero vector for database/operator checks."""
    if isinstance(dimension, bool) or not isinstance(dimension, int):
        raise ValueError("EMBEDDING_OUTPUT_DIMENSIONALITY must be an integer")
    if not 1 <= dimension <= _MAX_VECTOR_DIMENSIONS:
        raise ValueError(
            "EMBEDDING_OUTPUT_DIMENSIONALITY must be between 1 and "
            f"{_MAX_VECTOR_DIMENSIONS}"
        )

    values = []
    for index in range(dimension):
        digest = hashlib.sha256(f"{seed_id}:{index}".encode("utf-8")).digest()
        values.append((int.from_bytes(digest[:8], "big") / (2**64 - 1)) * 2 - 1)

    norm = math.sqrt(sum(value * value for value in values))
    return [value / norm for value in values]


def seed_pgvector(client, dimension: int) -> int:
    """Upsert smoke-test documents without touching application tenant data."""
    existing_dimensions = client.query_one(
        """
        SELECT MIN(vector_dims(embedding)) AS min_dimension,
               MAX(vector_dims(embedding)) AS max_dimension
        FROM research_documents
        WHERE NOT (
            tenant_id = :tenant_id
            AND metadata->>'seed_source' = :seed_source
        )
        """,
        {"tenant_id": SEED_TENANT_ID, "seed_source": SEED_SOURCE},
    )
    if existing_dimensions is None:
        raise RuntimeError("Could not inspect existing pgvector dimensions")
    min_dimension = existing_dimensions["min_dimension"]
    max_dimension = existing_dimensions["max_dimension"]
    if min_dimension is not None and (
        min_dimension != dimension or max_dimension != dimension
    ):
        raise ValueError(
            "Existing research-document vectors use dimension "
            f"{min_dimension}-{max_dimension}; refusing to seed dimension {dimension}"
        )

    statement = """
        INSERT INTO research_documents (
            id, tenant_id, content, metadata, embedding
        ) VALUES (
            :id::uuid,
            :tenant_id,
            :content,
            CAST(:metadata AS jsonb),
            CAST(:embedding AS vector)
        )
        ON CONFLICT (id) DO UPDATE SET
            tenant_id = EXCLUDED.tenant_id,
            content = EXCLUDED.content,
            metadata = EXCLUDED.metadata,
            embedding = EXCLUDED.embedding
        RETURNING id
    """

    for document in SEED_DOCUMENTS:
        seed_id = document["seed_id"]
        row_id = uuid.uuid5(uuid.NAMESPACE_URL, f"{SEED_SOURCE}:{seed_id}")
        metadata = {
            "seed_source": SEED_SOURCE,
            "seed_id": seed_id,
            "synthetic_embedding": True,
        }
        rows = client.query(
            statement,
            {
                "id": str(row_id),
                "tenant_id": SEED_TENANT_ID,
                "content": document["content"],
                "metadata": json.dumps(metadata),
                "embedding": "["
                + ",".join(
                    repr(value)
                    for value in build_seed_embedding(seed_id, dimension)
                )
                + "]",
            },
        )
        if not rows:
            raise RuntimeError(f"pgvector seed insert returned no ID for {seed_id}")

    return len(SEED_DOCUMENTS)


def main() -> int:
    load_dotenv()
    configured_dimension = os.environ.get("EMBEDDING_OUTPUT_DIMENSIONALITY")
    if not configured_dimension:
        print(
            "Set EMBEDDING_OUTPUT_DIMENSIONALITY to the verified embedding model "
            "dimension before seeding pgvector."
        )
        return 1

    try:
        dimension = int(configured_dimension)
        build_seed_embedding("dimension-check", dimension)
    except ValueError as error:
        print(f"Invalid EMBEDDING_OUTPUT_DIMENSIONALITY: {error}")
        return 1

    database = Database()
    try:
        count = seed_pgvector(database.client, dimension)
        print(
            f"Seeded {count} pgvector smoke-test documents "
            f"({dimension} dimensions) for tenant {SEED_TENANT_ID}."
        )
        print(
            "These synthetic vectors verify storage and distance queries only; "
            "they do not represent semantic embeddings."
        )
        return 0
    finally:
        database.client.close()


if __name__ == "__main__":
    sys.exit(main())
