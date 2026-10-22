"""Researcher tools for authenticated calls to the private GCP ingestion service."""

import os
import re
from typing import Any, Dict, Optional
from urllib.parse import urlsplit

import httpx
from agents import function_tool
from google.auth.transport.requests import AuthorizedSession, Request
from google.oauth2.id_token import fetch_id_token_credentials
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

_TENANT_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


class TransientIngestionError(RuntimeError):
    """The ingestion endpoint returned a retryable server or rate-limit error."""


class GCPIngestionClient:
    """Call the private GCP ingestion Cloud Run service with an ID token."""

    def __init__(
        self,
        endpoint: Optional[str] = None,
        tenant_id: Optional[str] = None,
        session=None,
    ):
        self.endpoint = (
            endpoint or os.environ.get("ALEX_INGESTION_URL", "")
        ).rstrip("/")
        self.tenant_id = (
            tenant_id
            if tenant_id is not None
            else os.environ.get("RESEARCH_TENANT_ID", "public_research")
        )

        parsed = urlsplit(self.endpoint)
        if (
            parsed.scheme != "https"
            or not parsed.netloc
            or parsed.path not in {"", "/"}
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "ALEX_INGESTION_URL must be an HTTPS Cloud Run service base URL"
            )
        if not _TENANT_ID_PATTERN.fullmatch(self.tenant_id):
            raise ValueError(
                "RESEARCH_TENANT_ID must contain 1-128 letters, numbers, "
                "underscores, or hyphens"
            )

        audience = os.environ.get("ALEX_INGESTION_AUDIENCE") or self.endpoint
        self.session = (
            session
            if session is not None
            else self._create_authorized_session(audience)
        )

    @staticmethod
    def _create_authorized_session(audience: str):
        credentials = fetch_id_token_credentials(audience, Request())
        return AuthorizedSession(credentials)

    @retry(
        retry=retry_if_exception(
            lambda error: isinstance(error, (httpx.TransportError, TransientIngestionError))
        ),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    def _post_with_retries(self, document: Dict[str, Any]) -> Dict[str, Any]:
        response = self.session.post(
            f"{self.endpoint}/ingest",
            json={
                "text": document["text"],
                "tenant_id": self.tenant_id,
                "metadata": document["metadata"],
            },
            timeout=30,
        )
        if response.status_code == 429 or response.status_code >= 500:
            raise TransientIngestionError(
                f"Ingestion service returned HTTP {response.status_code}"
            )
        response.raise_for_status()
        return response.json()

    def ingest(self, topic: str, analysis: str) -> Dict[str, Any]:
        if not isinstance(topic, str) or not topic.strip():
            raise ValueError("topic must be a non-empty string")
        if not isinstance(analysis, str) or not analysis.strip():
            raise ValueError("analysis must be a non-empty string")
        if len(analysis) > 20_000:
            raise ValueError("analysis must not exceed 20,000 characters")

        result = self._post_with_retries(
            {
                "text": analysis,
                "metadata": {"topic": topic.strip()},
            }
        )
        document_id = result.get("document_id")
        if not document_id:
            raise RuntimeError("Ingestion service response omitted document_id")
        return {
            "success": True,
            "document_id": document_id,
            "message": f"Stored research for {topic.strip()}",
        }


def _get_ingestion_client() -> GCPIngestionClient:
    return GCPIngestionClient()


@function_tool
def ingest_financial_document(topic: str, analysis: str) -> Dict[str, Any]:
    """Store concise market research in the tenant-scoped GCP knowledge base.

    Args:
        topic: The investment topic or subject of the research.
        analysis: The research summary and its sources, facts, and caveats.
    """
    return _get_ingestion_client().ingest(topic, analysis)
