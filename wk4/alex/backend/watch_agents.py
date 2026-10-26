#!/usr/bin/env python3
"""
Watch / tail logs from the Alex agent Cloud Run services in real time.

GCP equivalent of the former CloudWatch Logs watcher.

Usage:
    # Tail all agent services (requires gcloud auth):
    uv run watch_agents.py

    # Or use gcloud directly per service:
    gcloud run services logs tail alex-planner --project=<PROJECT>

Requirements:
    pip install google-cloud-logging
    gcloud auth application-default login
"""

import os
import sys
import threading
import time
from datetime import datetime, timezone, timedelta

try:
    from google.cloud import logging as gcloud_logging
    from google.cloud.logging_v2.services.logging_service_v2 import LoggingServiceV2Client
except ImportError:
    print("❌ google-cloud-logging not installed.")
    print("   pip install google-cloud-logging")
    sys.exit(1)

PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCP_PROJECT")
if not PROJECT:
    print("❌ Set GOOGLE_CLOUD_PROJECT env var.")
    sys.exit(1)

SERVICES = ["planner", "tagger", "reporter", "charter", "retirement"]
POLL_INTERVAL = 5  # seconds between log fetches


def tail_service(service_name: str, client: gcloud_logging.Client, stop_event: threading.Event):
    """Poll Cloud Logging for a specific Cloud Run service."""
    resource_filter = (
        f'resource.type="cloud_run_revision" '
        f'resource.labels.service_name="alex-{service_name}"'
    )
    since = datetime.now(timezone.utc) - timedelta(minutes=1)

    while not stop_event.is_set():
        since_str = since.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        log_filter = f'{resource_filter} timestamp>="{since_str}"'

        try:
            entries = list(client.list_entries(filter_=log_filter, order_by=gcloud_logging.ASCENDING, page_size=50))
            for entry in entries:
                ts = entry.timestamp.strftime("%H:%M:%S")
                severity = (entry.severity or "").ljust(8)
                payload = entry.payload if isinstance(entry.payload, str) else str(entry.payload)
                print(f"[{service_name:12}] {ts} {severity} {payload[:200]}")
                since = max(since, entry.timestamp)
        except Exception as exc:
            print(f"[{service_name:12}] ⚠️  Log fetch error: {exc}")

        time.sleep(POLL_INTERVAL)


def main():
    print("=" * 70)
    print("👁️  Alex Agent Log Watcher — GCP Cloud Run")
    print("=" * 70)
    print(f"Project: {PROJECT}")
    print(f"Services: {', '.join(f'alex-{s}' for s in SERVICES)}")
    print(f"Poll interval: {POLL_INTERVAL}s")
    print("Press Ctrl+C to stop.\n")

    client = gcloud_logging.Client(project=PROJECT)
    stop_event = threading.Event()

    threads = [
        threading.Thread(target=tail_service, args=(svc, client, stop_event), daemon=True)
        for svc in SERVICES
    ]

    for t in threads:
        t.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n👋 Stopping log watcher...")
        stop_event.set()


if __name__ == "__main__":
    main()
