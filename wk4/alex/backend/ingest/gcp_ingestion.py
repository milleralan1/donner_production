"""Document ingestion and semantic retrieval using Cloud SQL with pgvector."""

import json
import math
import os
import re
from typing import Any, List, Optional

from embedding_client import create_embedding_client
from src import Database

_TENANT_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_MAX_TEXT_LENGTH = 20_000
_MAX_NEIGHBORS = 100


class GCPIngestionService:
    """Store documents and embeddings in Cloud SQL using pgvector."""

    def __init__(
        self,
        embedding_client=None,
        database=None,
        embedding_dimension: Optional[int] = None,
    ):
        configured_dimension = embedding_dimension or os.environ.get(
            "EMBEDDING_OUTPUT_DIMENSIONALITY"
        )
        try:
            self.embedding_dimension = (
                int(configured_dimension) if configured_dimension else None
            )
        except ValueError as error:
            raise ValueError(
                "EMBEDDING_OUTPUT_DIMENSIONALITY must be a positive integer"
            ) from error

        missing = [
            name
            for name, value in (
                ("EMBEDDING_OUTPUT_DIMENSIONALITY", self.embedding_dimension),
            )
            if not value
        ]
        if missing:
            raise ValueError("Missing ingestion configuration: " + ", ".join(missing))
        if self.embedding_dimension <= 0:
            raise ValueError("EMBEDDING_OUTPUT_DIMENSIONALITY must be positive")

        self.embedding_client = embedding_client or create_embedding_client()
        self.database = database or Database()

    @staticmethod
    def _validate_tenant_id(tenant_id: str) -> str:
        if not isinstance(tenant_id, str) or not _TENANT_ID_PATTERN.fullmatch(
            tenant_id
        ):
            raise ValueError(
                "tenant_id must contain 1-128 letters, numbers, underscores, or hyphens"
            )
        return tenant_id

    @staticmethod
    def _validate_metadata(metadata: Optional[dict]) -> dict:
        if metadata is None:
            return {}
        if not isinstance(metadata, dict):
            raise ValueError("metadata must be a JSON object")
        if any(not isinstance(key, str) for key in metadata):
            raise ValueError("metadata keys must be strings")
        try:
            serialized = json.dumps(metadata, allow_nan=False)
        except (TypeError, ValueError) as error:
            raise ValueError("metadata must contain only valid JSON values") from error
        if len(serialized.encode("utf-8")) > 16_384:
            raise ValueError("metadata must not exceed 16 KiB")
        return metadata

    def ingest(
        self, text: str, tenant_id: str, metadata: Optional[dict] = None
    ) -> str:
        """Store a document and its embedding in the tenant-scoped vector table."""
        tenant_id = self._validate_tenant_id(tenant_id)
        if not isinstance(text, str) or not text.strip():
            raise ValueError("text must be a non-empty string")
        if len(text) > _MAX_TEXT_LENGTH:
            raise ValueError(f"text must not exceed {_MAX_TEXT_LENGTH} characters")
        metadata = self._validate_metadata(metadata)

        embedding = self.embedding_client.embed(
            text, task_type="RETRIEVAL_DOCUMENT"
        )
        self._validate_embedding_dimension(embedding)
        rows = self.database.client.query(
            """
            INSERT INTO research_documents (tenant_id, content, metadata, embedding)
            VALUES (
                :tenant_id,
                :content,
                CAST(:metadata AS jsonb),
                CAST(:embedding AS vector)
            )
            RETURNING id
            """,
            {
                "tenant_id": tenant_id,
                "content": text,
                "metadata": json.dumps(metadata, allow_nan=False),
                "embedding": self._serialize_embedding(embedding),
            },
        )
        if not rows:
            raise RuntimeError("Research document insert returned no ID")
        document_id = rows[0]["id"]
        return str(document_id)

    def search(
        self, query: str, tenant_id: str, limit: int = 5
    ) -> List[dict[str, Any]]:
        """Search only datapoints belonging to the supplied tenant."""
        tenant_id = self._validate_tenant_id(tenant_id)
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must be a non-empty string")
        if len(query) > _MAX_TEXT_LENGTH:
            raise ValueError(f"query must not exceed {_MAX_TEXT_LENGTH} characters")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= _MAX_NEIGHBORS:
            raise ValueError(f"limit must be an integer from 1 to {_MAX_NEIGHBORS}")

        embedding = self.embedding_client.embed(
            query, task_type="RETRIEVAL_QUERY"
        )
        self._validate_embedding_dimension(embedding)
        rows = self.database.client.query(
            """
            SELECT id, content, metadata,
                   embedding <=> CAST(:embedding AS vector) AS distance
            FROM research_documents
            WHERE tenant_id = :tenant_id
            ORDER BY embedding <=> CAST(:embedding AS vector)
            LIMIT :limit
            """,
            {
                "embedding": self._serialize_embedding(embedding),
                "tenant_id": tenant_id,
                "limit": limit,
            },
        )

        matches = []
        for row in rows:
            distance = row.get("distance")
            if not isinstance(distance, (float, int)) or not math.isfinite(distance):
                continue
            document_metadata = row.get("metadata") or {}
            if isinstance(document_metadata, str):
                document_metadata = json.loads(document_metadata)
            matches.append(
                {
                    "id": str(row["id"]),
                    "distance": float(distance),
                    "text": row["content"],
                    "metadata": document_metadata,
                }
            )
        return matches

    @staticmethod
    def _serialize_embedding(embedding: List[float]) -> str:
        return "[" + ",".join(repr(float(value)) for value in embedding) + "]"

    def _validate_embedding_dimension(self, embedding: List[float]) -> None:
        if len(embedding) != self.embedding_dimension:
            raise ValueError(
                "Embedding dimension mismatch: expected "
                f"{self.embedding_dimension}, received {len(embedding)}"
            )
