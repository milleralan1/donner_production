"""Pub/Sub publishing helper used by the GCP API deployment."""

from google.cloud import pubsub_v1


def publish_analysis_job(topic: str, job_id: str, publisher=None) -> str:
    """Publish only the trusted database job ID and wait for publish confirmation."""
    if not topic.startswith("projects/") or "/topics/" not in topic:
        raise ValueError("PUBSUB_TOPIC must be a fully qualified topic resource name")
    if not job_id:
        raise ValueError("job_id is required")

    publisher = publisher or pubsub_v1.PublisherClient()
    future = publisher.publish(topic, job_id=job_id)
    return future.result(timeout=30)
