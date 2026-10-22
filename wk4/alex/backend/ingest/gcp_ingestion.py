"""GCP document ingestion and retrieval using Cloud Storage and Vertex AI."""

import json
import math
import os
import re
import uuid
from typing import Any, List, Optional
from urllib.parse import quote, urlsplit

from vertex_embeddings import VertexEmbeddingClient

_TENANT_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_MAX_TEXT_LENGTH = 20_000
_MAX_NEIGHBORS = 100
_API_SCOPE = "https://www.googleapis.com/auth/cloud-platform"
_API_BASE = "https://aiplatform.googleapis.com/v1"


class GCPIngestionService:
    """Store source documents in GCS and vectors in a Vertex AI Vector Search index."""

    def __init__(
        self,
        embedding_client=None,
        storage_client=None,
        authorized_session=None,
        project: Optional[str] = None,
        region: Optional[str] = None,
        embedding_dimension: Optional[int] = None,
        bucket_name: Optional[str] = None,
        index_id: Optional[str] = None,
        index_endpoint_id: Optional[str] = None,
        deployed_index_id: Optional[str] = None,
        public_endpoint_domain: Optional[str] = None,
    ):
        self.project = project or os.environ.get("GOOGLE_CLOUD_PROJECT")
        self.region = (
            region
            or os.environ.get("GOOGLE_CLOUD_REGION")
            or os.environ.get("GOOGLE_CLOUD_LOCATION")
        )
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
        self.bucket_name = bucket_name or os.environ.get("DOCUMENT_BUCKET")
        self.index_id = index_id or os.environ.get("VECTOR_INDEX_ID")
        self.index_endpoint_id = index_endpoint_id or os.environ.get(
            "VECTOR_INDEX_ENDPOINT_ID"
        )
        self.deployed_index_id = deployed_index_id or os.environ.get(
            "VECTOR_DEPLOYED_INDEX_ID"
        )
        self.public_endpoint_domain = (
            public_endpoint_domain
            or os.environ.get("VECTOR_PUBLIC_ENDPOINT_DOMAIN")
        )

        missing = [
            name
            for name, value in (
                ("GOOGLE_CLOUD_PROJECT", self.project),
                ("GOOGLE_CLOUD_REGION", self.region),
                ("EMBEDDING_OUTPUT_DIMENSIONALITY", self.embedding_dimension),
                ("DOCUMENT_BUCKET", self.bucket_name),
                ("VECTOR_INDEX_ID", self.index_id),
                ("VECTOR_INDEX_ENDPOINT_ID", self.index_endpoint_id),
                ("VECTOR_DEPLOYED_INDEX_ID", self.deployed_index_id),
                ("VECTOR_PUBLIC_ENDPOINT_DOMAIN", self.public_endpoint_domain),
            )
            if not value
        ]
        if missing:
            raise ValueError("Missing GCP ingestion configuration: " + ", ".join(missing))
        if self.embedding_dimension <= 0:
            raise ValueError("EMBEDDING_OUTPUT_DIMENSIONALITY must be positive")

        self.embedding_client = embedding_client or VertexEmbeddingClient()

        if storage_client is None or authorized_session is None:
            try:
                import google.auth
                from google.auth.transport.requests import AuthorizedSession
                from google.cloud import storage
            except ImportError as error:
                raise ImportError(
                    "GCP ingestion requires the GCP extra. "
                    "Install with `uv sync --extra gcp`."
                ) from error

            credentials, _ = google.auth.default(scopes=[_API_SCOPE])
            if storage_client is None:
                storage_client = storage.Client(
                    project=self.project, credentials=credentials
                )
            if authorized_session is None:
                authorized_session = AuthorizedSession(credentials)

        self.storage_client = storage_client
        self.authorized_session = authorized_session
        self.bucket = self.storage_client.bucket(self.bucket_name)

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

    def _vector_index_url(self, action: str) -> str:
        project = quote(self.project, safe="")
        region = quote(self.region, safe="")
        index_id = quote(self.index_id, safe="")
        return (
            f"{_API_BASE}/projects/{project}/locations/{region}"
            f"/indexes/{index_id}:{action}"
        )

    def _search_url(self) -> str:
        project = quote(self.project, safe="")
        region = quote(self.region, safe="")
        endpoint = quote(self.index_endpoint_id, safe="")
        domain = self.public_endpoint_domain.strip().rstrip("/")
        parsed_domain = urlsplit(
            domain if "://" in domain else f"//{domain}"
        )
        hostname = parsed_domain.hostname
        if (
            parsed_domain.scheme not in {"", "https"}
            or not hostname
            or parsed_domain.username
            or parsed_domain.password
            or parsed_domain.path
            or parsed_domain.query
            or parsed_domain.fragment
            or not hostname.endswith(".vdb.vertexai.goog")
        ):
            raise ValueError(
                "VECTOR_PUBLIC_ENDPOINT_DOMAIN must be a Vertex AI Vector Search "
                "HTTPS endpoint domain"
            )
        return (
            f"https://{hostname}/v1/projects/{project}/locations/{region}"
            f"/indexEndpoints/{endpoint}:findNeighbors"
        )

    @staticmethod
    def _raise_for_response(response, operation: str):
        if response.status_code < 200 or response.status_code >= 300:
            raise RuntimeError(
                f"Vertex AI {operation} failed with HTTP {response.status_code}"
            )

    def ingest(
        self, text: str, tenant_id: str, metadata: Optional[dict] = None
    ) -> str:
        """Store a document and upsert its embedding with a tenant namespace."""
        tenant_id = self._validate_tenant_id(tenant_id)
        if not isinstance(text, str) or not text.strip():
            raise ValueError("text must be a non-empty string")
        if len(text) > _MAX_TEXT_LENGTH:
            raise ValueError(f"text must not exceed {_MAX_TEXT_LENGTH} characters")
        metadata = self._validate_metadata(metadata)

        document_id = str(uuid.uuid4())
        payload = {
            "document_id": document_id,
            "tenant_id": tenant_id,
            "text": text,
            "metadata": metadata,
        }
        blob = self.bucket.blob(f"{tenant_id}/{document_id}.json")
        blob.upload_from_string(
            json.dumps(payload, allow_nan=False),
            content_type="application/json",
        )

        try:
            embedding = self.embedding_client.embed(
                text, task_type="RETRIEVAL_DOCUMENT"
            )
            if len(embedding) != self.embedding_dimension:
                raise ValueError(
                    "Embedding dimension mismatch: expected "
                    f"{self.embedding_dimension}, received {len(embedding)}"
                )
            response = self.authorized_session.post(
                self._vector_index_url("upsertDatapoints"),
                json={
                    "datapoints": [
                        {
                            "datapointId": document_id,
                            "featureVector": embedding,
                            "restricts": [
                                {
                                    "namespace": "tenant_id",
                                    "allowList": [tenant_id],
                                }
                            ],
                        }
                    ]
                },
                timeout=30,
            )
            self._raise_for_response(response, "vector upsert")
        except Exception:
            blob.delete()
            raise
        return document_id

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
        if len(embedding) != self.embedding_dimension:
            raise ValueError(
                "Embedding dimension mismatch: expected "
                f"{self.embedding_dimension}, received {len(embedding)}"
            )
        response = self.authorized_session.post(
            self._search_url(),
            json={
                "deployedIndexId": self.deployed_index_id,
                "queries": [
                    {
                        "datapoint": {
                            "featureVector": embedding,
                            "restricts": [
                                {
                                    "namespace": "tenant_id",
                                    "allowList": [tenant_id],
                                }
                            ],
                        },
                        "neighborCount": limit,
                    }
                ],
            },
            timeout=30,
        )
        self._raise_for_response(response, "vector search")

        result = response.json()
        neighbors = (
            result.get("nearestNeighbors", [{}])[0].get("neighbors", [])
            if result.get("nearestNeighbors")
            else []
        )
        matches = []
        for neighbor in neighbors:
            datapoint_id = neighbor.get("datapoint", {}).get("datapointId")
            distance = neighbor.get("distance")
            if not datapoint_id or not isinstance(distance, (float, int)):
                continue
            if not math.isfinite(distance):
                continue

            blob = self.bucket.blob(f"{tenant_id}/{datapoint_id}.json")
            if not blob.exists():
                continue
            document = json.loads(blob.download_as_text())
            if document.get("tenant_id") != tenant_id:
                continue
            matches.append(
                {
                    "id": datapoint_id,
                    "distance": float(distance),
                    "text": document["text"],
                    "metadata": document.get("metadata", {}),
                }
            )
        return matches
