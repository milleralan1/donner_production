"""Authenticated Cloud Run entrypoint shared by the five GCP agent services."""

import asyncio
import base64
import binascii
import importlib
import json
import logging
import os
from typing import Any, Callable, Optional

from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


class AgentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: Optional[str] = Field(default=None, min_length=1, max_length=128)
    instruments: Optional[list[dict[str, Any]]] = Field(default=None, max_length=50)
    portfolio_data: Optional[dict[str, Any]] = None
    user_data: Optional[dict[str, Any]] = None


def _get_agent_handler() -> Callable:
    module = importlib.import_module("lambda_handler")
    handler = getattr(module, "lambda_handler", None)
    if not callable(handler):
        raise RuntimeError("Agent module has no callable lambda_handler")
    return handler


def _get_agent_role() -> str:
    role = os.environ.get("ALEX_AGENT_ROLE", "").strip().lower()
    if role not in {"planner", "tagger", "reporter", "charter", "retirement"}:
        raise HTTPException(status_code=503, detail="Agent role is not configured")
    return role


async def _invoke(handler: Callable, event: dict) -> dict:
    try:
        result = await asyncio.to_thread(handler, event, None)
    except Exception as error:
        logger.error("Agent execution raised %s", type(error).__name__)
        raise HTTPException(status_code=502, detail="Agent execution failed") from error

    status_code = result.get("statusCode", 500) if isinstance(result, dict) else 500
    body = result.get("body", {}) if isinstance(result, dict) else {}
    if status_code < 200 or status_code >= 300:
        logger.error("Agent execution returned HTTP %s", status_code)
        raise HTTPException(status_code=502, detail="Agent execution failed")

    if isinstance(body, str):
        try:
            body = json.loads(body)
        except json.JSONDecodeError:
            body = {"message": body}
    if not isinstance(body, dict):
        raise HTTPException(status_code=502, detail="Agent returned an invalid response")
    return body


def create_app(handler_getter: Callable[[], Callable] = _get_agent_handler) -> FastAPI:
    app = FastAPI(title="Alex GCP Agent", docs_url=None, redoc_url=None)

    @app.get("/healthz")
    async def health():
        return {"status": "healthy", "role": _get_agent_role()}

    @app.post("/invoke")
    async def invoke(request: AgentRequest):
        role = _get_agent_role()
        event = request.model_dump(exclude_none=True)
        if role != "tagger" and not event.get("job_id"):
            raise HTTPException(status_code=422, detail="job_id is required")
        if role == "tagger" and not (
            event.get("job_id") or event.get("instruments")
        ):
            raise HTTPException(
                status_code=422, detail="job_id or instruments is required"
            )
        return await _invoke(handler_getter(), event)

    @app.post("/pubsub", status_code=204)
    async def pubsub(envelope: dict):
        if _get_agent_role() != "planner":
            raise HTTPException(status_code=404, detail="Not found")
        message = envelope.get("message")
        encoded_data = message.get("data") if isinstance(message, dict) else None
        if not isinstance(encoded_data, str):
            raise HTTPException(status_code=400, detail="Pub/Sub message data is required")

        try:
            payload = json.loads(base64.b64decode(encoded_data, validate=True))
        except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise HTTPException(status_code=400, detail="Invalid Pub/Sub message data") from error
        if not isinstance(payload, dict) or not isinstance(payload.get("job_id"), str):
            raise HTTPException(status_code=400, detail="Pub/Sub job_id is required")

        await _invoke(handler_getter(), {"job_id": payload["job_id"]})
        return Response(status_code=204)

    return app


app = create_app()
