"""GCP Cloud Scheduler HTTP handler for triggering the researcher service.

Cloud Scheduler can POST directly to the researcher Cloud Run URL with OIDC
authentication, so this intermediary is optional.

    gcloud scheduler jobs create http alex-research-trigger \
      --schedule="0 */6 * * *" \
      --uri="${RESEARCHER_SERVICE_URL}/research" \
      --message-body='{}' \
      --oidc-service-account-email="${SCHEDULER_SA_EMAIL}" \
      --oidc-token-audience="${RESEARCHER_SERVICE_URL}" \
      --location="${REGION}"

  Option B — Use this file as a Cloud Run entrypoint if you want a thin proxy
    (e.g. to add pre-processing or fan-out to multiple services).
    Deploy this as a Cloud Run service and point Cloud Scheduler at it.

This file implements Option B for completeness.
"""

import json
import logging
import os

import google.auth.transport.requests
import google.oauth2.id_token
import requests
from fastapi import FastAPI, Response

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Alex Scheduler", docs_url=None, redoc_url=None)


def _call_researcher() -> dict:
    """POST to the researcher Cloud Run service with a Google-signed OIDC token."""
    researcher_url = os.environ.get("RESEARCHER_SERVICE_URL", "").rstrip("/")
    if not researcher_url.startswith("https://"):
        raise ValueError("RESEARCHER_SERVICE_URL must be an HTTPS URL")

    audience = os.environ.get("RESEARCHER_SERVICE_AUDIENCE") or researcher_url
    auth_req = google.auth.transport.requests.Request()
    id_token = google.oauth2.id_token.fetch_id_token(auth_req, audience)

    endpoint = f"{researcher_url}/research"
    response = requests.post(
        endpoint,
        json={},
        headers={"Authorization": f"Bearer {id_token}", "Content-Type": "application/json"},
        timeout=300,
    )
    response.raise_for_status()
    return response.json()


@app.get("/healthz")
async def health():
    return {"status": "healthy", "service": "scheduler"}


@app.post("/trigger-research", status_code=204)
async def trigger_research():
    """
    Called by Cloud Scheduler to kick off the researcher service.
    Cloud Scheduler sends an OIDC-authenticated POST to this endpoint.
    """
    try:
        result = _call_researcher()
        logger.info("Research triggered successfully: %s", json.dumps(result)[:200])
    except Exception as exc:
        logger.error("Failed to trigger research: %s", exc)
        return Response(status_code=502, content=f"Failed to trigger research: {exc}")
    return Response(status_code=204)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
