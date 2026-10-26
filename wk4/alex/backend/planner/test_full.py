#!/usr/bin/env python3
"""
Full end-to-end test of the Planner agent orchestration via GCP Pub/Sub.

Publishes a test job through the GCP Pub/Sub queue.

Usage:
    cd backend/planner
    uv run test_full.py
"""

import json
import logging
import os
import sys
import time
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv(override=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Add parent to path so we can import api.gcp_queue
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src import Database

db = Database()

PUBSUB_TOPIC = os.getenv("PUBSUB_TOPIC", "alex-analysis-jobs")


def publish_job(job_id: str) -> str:
    """Publish job_id to Pub/Sub topic."""
    from api.gcp_queue import publish_analysis_job
    return publish_analysis_job(PUBSUB_TOPIC, job_id)


def main():
    print("=" * 70)
    print("🎯 Alex Planner Orchestration - Full Test (GCP Pub/Sub)")
    print("=" * 70)

    project = os.getenv("GOOGLE_CLOUD_PROJECT", "not-set")
    print(f"GCP Project:   {project}")
    print(f"Pub/Sub Topic: {PUBSUB_TOPIC}")
    print(f"LLM Provider:  {os.getenv('ALEX_LLM_PROVIDER', 'groq')}")
    print(f"Groq Model:    {os.getenv('GROQ_MODEL', 'not-set')}")
    print()

    test_user_id = "test_user_001"
    user = db.users.find_by_clerk_id(test_user_id)
    if not user:
        print(
            "❌ Test user not found. Run database setup first:\n"
            "   cd ../database && uv run reset_db.py --with-test-data"
        )
        return 1

    accounts = db.accounts.find_by_user(test_user_id)
    total_positions = sum(len(db.positions.find_by_account(a["id"])) for a in accounts)
    print(f"✓ Portfolio: {len(accounts)} accounts, {total_positions} positions")

    print("\n🚀 Creating test job...")
    job_id = db.jobs.create(
        {
            "clerk_user_id": test_user_id,
            "job_type": "portfolio_analysis",
            "status": "pending",
            "request_payload": {
                "analysis_type": "full",
                "requested_at": datetime.now(timezone.utc).isoformat(),
                "test_run": True,
            },
        }
    )
    print(f"✓ Created job: {job_id}")

    print("\n📤 Publishing to Pub/Sub...")
    try:
        msg_id = publish_job(job_id)
        print(f"✓ Message published: {msg_id}")
    except Exception as exc:
        print(f"❌ Failed to publish: {exc}")
        return 1

    print("\n⏳ Monitoring job (timeout: 5 min)...")
    print("-" * 50)

    start = time.time()
    last_status = None

    while time.time() - start < 300:
        job = db.jobs.find_by_id(job_id)
        status = job["status"]

        if status != last_status:
            elapsed = int(time.time() - start)
            print(f"[{elapsed:3d}s] Status: {status}")
            last_status = status

        if status == "completed":
            print("-" * 50)
            print("✅ Job completed!")
            _print_summary(job)
            return 0
        elif status == "failed":
            print("-" * 50)
            print(f"❌ Job failed: {job.get('error_message', 'unknown')}")
            return 1

        time.sleep(3)

    print("-" * 50)
    print("❌ Timed out")
    return 1


def _print_summary(job: dict) -> None:
    print("\n" + "=" * 70)
    print("📋 RESULTS")
    print("=" * 70)

    for key, label, emoji in [
        ("summary_payload", "Orchestrator Summary", "🎯"),
        ("report_payload", "Portfolio Report", "📝"),
        ("charts_payload", "Visualizations", "📊"),
        ("retirement_payload", "Retirement Analysis", "🏖️"),
    ]:
        payload = job.get(key)
        if payload:
            print(f"\n{emoji} {label}: ✅")
            if isinstance(payload, dict):
                for k, v in list(payload.items())[:3]:
                    print(f"   {k}: {str(v)[:80]}")
        else:
            print(f"\n{emoji} {label}: ❌ missing")


if __name__ == "__main__":
    exit(main())
