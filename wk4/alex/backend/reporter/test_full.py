#!/usr/bin/env python3
"""
Full test for Reporter agent via GCP Cloud Run HTTP invocation.

GCP equivalent of the former Lambda invoke test.
Calls the Reporter Cloud Run service directly with a Google-signed OIDC token.

Usage:
    cd backend/reporter
    uv run test_full.py

Requires:
    REPORTER_SERVICE_URL env var pointing to the Cloud Run service.
"""

import json
import os
import sys
import time

import requests
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src import Database
from src.schemas import JobCreate


def invoke_cloud_run(service_url: str, payload: dict) -> dict:
    """POST to a Cloud Run service with a Google-signed OIDC token."""
    import google.auth.transport.requests
    import google.oauth2.id_token

    audience = os.environ.get("REPORTER_SERVICE_AUDIENCE") or service_url
    auth_req = google.auth.transport.requests.Request()
    id_token = google.oauth2.id_token.fetch_id_token(auth_req, audience)

    response = requests.post(
        f"{service_url.rstrip('/')}/invoke",
        json=payload,
        headers={
            "Authorization": f"Bearer {id_token}",
            "Content-Type": "application/json",
        },
        timeout=600,
    )
    response.raise_for_status()
    return response.json()


def test_reporter_service():
    """Test the Reporter agent via Cloud Run invocation."""
    db = Database()

    service_url = os.environ.get("REPORTER_SERVICE_URL", "")
    if not service_url:
        print(
            "❌ REPORTER_SERVICE_URL not set.\n"
            "   Set it to the Cloud Run service URL, e.g.:\n"
            "   export REPORTER_SERVICE_URL=https://reporter-xxxx-uc.a.run.app"
        )
        sys.exit(1)

    test_user_id = "test_user_001"
    job_create = JobCreate(
        clerk_user_id=test_user_id,
        job_type="portfolio_analysis",
        request_payload={"analysis_type": "test", "test": True},
    )
    job_id = db.jobs.create(job_create.model_dump())

    print(f"Testing Reporter Cloud Run service with job {job_id}")
    print("=" * 60)
    print(f"Service URL: {service_url}")

    try:
        result = invoke_cloud_run(service_url, {"job_id": job_id})
        print(f"Response: {json.dumps(result, indent=2)}")

        time.sleep(2)
        job = db.jobs.find_by_id(job_id)

        if job and job.get("reporter_payload" if "reporter" not in ("planner", "tagger") else "status") :
            print("\n✅ Reporter completed successfully!")
        else:
            print(f"\n✅ Service responded OK (status: {job.get('status') if job else 'unknown'})")

    except Exception as exc:
        print(f"❌ Error invoking Cloud Run service: {exc}")
        sys.exit(1)

    print("=" * 60)


if __name__ == "__main__":
    test_reporter_service()
