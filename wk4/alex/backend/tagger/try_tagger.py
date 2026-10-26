#!/usr/bin/env python3
"""
Quick smoke-test: invoke the Tagger Cloud Run service directly.

Directly invokes the deployed GCP Tagger service.

Usage:
    cd backend/tagger
    TAGGER_SERVICE_URL=https://alex-tagger-xxx.run.app uv run try_tagger.py
"""

import json
import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv(override=True)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src import Database


def invoke_tagger(service_url: str, payload: dict) -> dict:
    """Call the Tagger Cloud Run service with a Google-signed OIDC token."""
    import google.auth.transport.requests
    import google.oauth2.id_token

    audience = os.environ.get("TAGGER_SERVICE_AUDIENCE") or service_url
    auth_req = google.auth.transport.requests.Request()
    id_token = google.oauth2.id_token.fetch_id_token(auth_req, audience)

    resp = requests.post(
        f"{service_url.rstrip('/')}/invoke",
        json=payload,
        headers={"Authorization": f"Bearer {id_token}", "Content-Type": "application/json"},
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()


def main():
    service_url = os.environ.get("TAGGER_SERVICE_URL", "")
    if not service_url:
        print("❌ Set TAGGER_SERVICE_URL to the Cloud Run service URL")
        sys.exit(1)

    print(f"Tagger Cloud Run URL: {service_url}")

    # Test with a small instrument list
    test_instruments = [
        {"symbol": "AAPL", "name": "Apple Inc."},
        {"symbol": "MSFT", "name": "Microsoft Corporation"},
        {"symbol": "BTC-USD", "name": "Bitcoin USD"},
    ]

    print(f"Testing with {len(test_instruments)} instruments...")
    result = invoke_tagger(service_url, {"instruments": test_instruments})
    print(f"\nResult:\n{json.dumps(result, indent=2)}")


if __name__ == "__main__":
    main()
