"""Private Cloud Run HTTP service for GCP document ingestion and search."""

import logging
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from gcp_ingestion import GCPIngestionService

logger = logging.getLogger(__name__)


class DocumentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=20_000)
    tenant_id: str = Field(min_length=1, max_length=128)
    metadata: Optional[dict] = None

    @field_validator("text", "tenant_id")
    @classmethod
    def reject_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=20_000)
    tenant_id: str = Field(min_length=1, max_length=128)
    limit: int = Field(default=5, ge=1, le=100)

    @field_validator("query", "tenant_id")
    @classmethod
    def reject_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value


def create_app(service=None) -> FastAPI:
    application = FastAPI(title="Alex GCP Ingestion", docs_url=None, redoc_url=None)
    ingestion_service = service

    def get_service():
        nonlocal ingestion_service
        if ingestion_service is None:
            ingestion_service = GCPIngestionService()
        return ingestion_service

    @application.get("/healthz")
    def health():
        return {"status": "ok"}

    @application.post("/ingest", status_code=201)
    def ingest_document(request: DocumentRequest):
        try:
            document_id = get_service().ingest(
                text=request.text,
                tenant_id=request.tenant_id,
                metadata=request.metadata,
            )
            return {"document_id": document_id}
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except Exception as error:
            logger.error(
                "GCP document ingestion failed (%s)", type(error).__name__
            )
            raise HTTPException(
                status_code=502, detail="Document ingestion failed"
            ) from error

    @application.post("/search")
    def search_documents(request: SearchRequest):
        try:
            matches = get_service().search(
                query=request.query,
                tenant_id=request.tenant_id,
                limit=request.limit,
            )
            return {"results": matches, "count": len(matches)}
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except Exception as error:
            logger.error("GCP document search failed (%s)", type(error).__name__)
            raise HTTPException(status_code=502, detail="Document search failed") from error

    return application


app = create_app()
