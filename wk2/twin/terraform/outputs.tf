output "cloud_run_url" {
  description = "URL of the Cloud Run service"
  value       = google_cloud_run_v2_service.api.uri
}

output "gcs_memory_bucket" {
  description = "Name of the Cloud Storage bucket for memory storage"
  value       = google_storage_bucket.memory.name
}

output "service_account_email" {
  description = "Email of the runtime service account"
  value       = google_service_account.runtime.email
}

output "cloud_run_service_name" {
  description = "Name of the Cloud Run service"
  value       = google_cloud_run_v2_service.api.name
}
