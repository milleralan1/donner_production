#!/usr/bin/env python3
"""
Track Tagger Cloud Run service activity via GCP Cloud Logging.

GCP equivalent of the former CloudWatch Logs tracker.

Usage:
    cd backend/tagger
    uv run track_tagger.py
"""

import os
import sys
import time
from datetime import datetime, timezone, timedelta

try:
    from google.cloud import logging as gcloud_logging
except ImportError:
    print("❌ google-cloud-logging not installed: pip install google-cloud-logging")
    sys.exit(1)

PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
if not PROJECT:
    print("❌ Set GOOGLE_CLOUD_PROJECT env var.")
    sys.exit(1)


def stream_tagger_logs(minutes_back: int = 5, poll_interval: int = 3):
    """Stream logs from the Tagger Cloud Run service."""
    client = gcloud_logging.Client(project=PROJECT)

    log_filter = (
        'resource.type="cloud_run_revision" '
        'resource.labels.service_name="alex-tagger"'
    )

    since = datetime.now(timezone.utc) - timedelta(minutes=minutes_back)
    print(f"📋 Tagger Cloud Run Log Stream  (Project: {PROJECT})")
    print(f"   Showing logs from last {minutes_back} min. Ctrl+C to stop.\n")

    while True:
        since_str = since.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        full_filter = f'{log_filter} timestamp>="{since_str}"'

        try:
            entries = list(
                client.list_entries(
                    filter_=full_filter,
                    order_by=gcloud_logging.ASCENDING,
                    page_size=100,
                )
            )
            for entry in entries:
                ts = entry.timestamp.strftime("%H:%M:%S")
                payload = entry.payload if isinstance(entry.payload, str) else str(entry.payload)
                print(f"{ts}  {payload[:300]}")
                since = max(since, entry.timestamp)
        except Exception as exc:
            print(f"⚠️  {exc}")

        time.sleep(poll_interval)


if __name__ == "__main__":
    stream_tagger_logs()
