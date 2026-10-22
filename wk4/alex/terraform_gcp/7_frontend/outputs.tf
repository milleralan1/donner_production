output "api_url" {
  description = "Public HTTPS Cloud Run URL for the Clerk-authenticated API."
  value       = google_cloud_run_v2_service.api.uri
}

output "frontend_url" {
  description = "Public HTTPS Cloud Run URL for the Next.js application."
  value       = google_cloud_run_v2_service.frontend.uri
}

output "artifact_registry_repository" {
  description = "Regional Artifact Registry repository for API and frontend images."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.app.repository_id}"
}

output "pubsub_topic" {
  description = "Pub/Sub topic used by the API to queue analysis jobs."
  value       = "projects/${var.project_id}/topics/${var.pubsub_topic_id}"
}
