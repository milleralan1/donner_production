#!/usr/bin/env python3
"""Full end-to-end test via GCP Pub/Sub for the Alex platform.

Publishes a job to Pub/Sub (same as the API does) and polls Cloud SQL for
completion.

Usage:
    cd backend
    uv run test_full.py
"""

import json
import os
import time
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv(override=True)

from src import Database
from src.schemas import UserCreate, InstrumentCreate, AccountCreate, PositionCreate


def setup_test_data(db):
    """Ensure test user and portfolio exist."""
    print("Setting up test data...")

    test_user_id = "test_user_001"
    user = db.users.find_by_clerk_id(test_user_id)
    if not user:
        user_data = UserCreate(
            clerk_user_id=test_user_id,
            display_name="Test User",
            years_to_retirement=25,
            target_allocation={"stocks": 70, "bonds": 20, "alternatives": 10},
        )
        db.users.create(user_data.model_dump())
        print(f"  ✓ Created test user: {test_user_id}")
    else:
        print(f"  ✓ Test user exists: {test_user_id}")

    accounts = db.accounts.find_by_user(test_user_id)
    if not accounts:
        account_data = AccountCreate(
            clerk_user_id=test_user_id,
            account_name="Test 401(k)",
            account_type="401k",
            cash_balance=5000.00,
        )
        account_id = db.accounts.create(account_data.model_dump())
        print("  ✓ Created test account: Test 401(k)")

        for sym, qty in [("SPY", 100), ("QQQ", 50), ("BND", 200), ("VTI", 75)]:
            db.positions.create(
                PositionCreate(account_id=account_id, symbol=sym, quantity=qty).model_dump()
            )
        print("  ✓ Created 4 positions")
    else:
        n = sum(len(db.positions.find_by_account(a["id"])) for a in accounts)
        print(f"  ✓ Test account exists with {n} positions")

    return test_user_id


def publish_to_pubsub(topic: str, job_id: str) -> str:
    """Publish a job_id to the configured Pub/Sub topic."""
    from api.gcp_queue import publish_analysis_job  # reuse the production helper
    return publish_analysis_job(topic, job_id)


def main():
    print("=" * 70)
    print("🎯 Full End-to-End Test via GCP Pub/Sub")
    print("=" * 70)

    db = Database()

    pubsub_topic = os.getenv("PUBSUB_TOPIC", "")
    if not pubsub_topic:
        print("❌ PUBSUB_TOPIC env var not set. Cannot trigger analysis.")
        return 1

    print(f"Pub/Sub topic: {pubsub_topic}")

    test_user_id = setup_test_data(db)

    print("\nCreating analysis job...")
    job_data = {
        "clerk_user_id": test_user_id,
        "job_type": "portfolio_analysis",
        "status": "pending",
        "request_payload": {
            "analysis_type": "full",
            "requested_at": datetime.now(timezone.utc).isoformat(),
            "test_run": True,
            "include_retirement": True,
            "include_charts": True,
            "include_report": True,
        },
    }
    job_id = db.jobs.create(job_data)
    print(f"  ✓ Created job: {job_id}")

    print("\nTriggering analysis via Pub/Sub...")
    try:
        msg_id = publish_to_pubsub(pubsub_topic, job_id)
        print(f"  ✓ Message published: {msg_id}")
    except Exception as exc:
        print(f"  ❌ Failed to publish: {exc}")
        return 1

    print("\n⏳ Monitoring job progress...")
    print("-" * 50)

    start = time.time()
    timeout = 300  # 5 minutes (Cloud Run cold-start + agent work)
    last_status = None

    while time.time() - start < timeout:
        job = db.jobs.find_by_id(job_id)
        status = job["status"]

        if status != last_status:
            elapsed = int(time.time() - start)
            print(f"[{elapsed:3d}s] Status: {status}")
            last_status = status
            if status == "failed" and job.get("error_message"):
                print(f"       Error: {job['error_message']}")

        if status == "completed":
            print("-" * 50)
            print("\n✅ Job completed successfully!")
            _print_results(job)
            break
        elif status == "failed":
            print("-" * 50)
            print(f"\n❌ Job failed: {job.get('error_message', 'unknown')}")
            return 1

        time.sleep(3)
    else:
        print("-" * 50)
        print("\n❌ Job timed out after 5 minutes")
        return 1

    print(f"\n📋 Job ID: {job_id}  |  User: {test_user_id}")
    print(f"   Total time: {int(time.time() - start)}s")
    return 0


def _print_results(job: dict) -> None:
    if job.get("report_payload"):
        content = job["report_payload"].get("content", "")
        print(f"\n📝 Report: {len(content)} chars")
        print(f"   Preview: {content[:200]}...")
    else:
        print("\n❌ No report")

    if job.get("charts_payload"):
        charts = job["charts_payload"]
        print(f"\n📊 Charts: {len(charts)} visualizations")
        for k, v in charts.items():
            print(f"   - {k}: {v.get('title', 'untitled')}")
    else:
        print("\n❌ No charts")

    if job.get("retirement_payload"):
        ret = job["retirement_payload"]
        print(f"\n🎯 Retirement: success_rate={ret.get('success_rate', 'N/A')}%")
    else:
        print("\n❌ No retirement analysis")

    if job.get("summary_payload"):
        summary = job["summary_payload"]
        print(f"\n📋 Summary: {summary.get('summary', '')[:200]}")


if __name__ == "__main__":
    exit(main())
