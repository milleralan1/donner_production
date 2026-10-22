output "agent_service_urls" {
  description = "Private IAM-protected Cloud Run URLs for each agent."
  value       = { for role, service in google_cloud_run_v2_service.agent : role => service.uri }
}

output "artifact_registry_repository" {
  description = "Regional Artifact Registry Docker repository."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.agents.repository_id}"
}

output "jobs_topic" {
  description = "Pub/Sub topic for analysis job messages."
  value       = google_pubsub_topic.jobs.name
}

output "jobs_subscription" {
  description = "Authenticated push subscription delivering jobs to Planner."
  value       = google_pubsub_subscription.jobs.name
}

output "dead_letter_subscription" {
  description = "Subscription for inspecting messages routed to the dead-letter topic."
  value       = google_pubsub_subscription.dead_letter.name
}

output "pubsub_push_service_account" {
  description = "Service account used to authenticate Pub/Sub push requests."
  value       = google_service_account.pubsub_push.email
}
