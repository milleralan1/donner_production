output "dashboard_name" {
  description = "Cloud Monitoring dashboard display name."
  value       = "Alex service health"
}

output "dashboard_url" {
  description = "Google Cloud Console link to the Alex service health dashboard."
  value       = "https://console.cloud.google.com/monitoring/dashboards?project=${var.project_id}"
}

output "alert_policy_names" {
  description = "Created alert policy display names."
  value = concat(
    [google_monitoring_alert_policy.cloud_run_errors.display_name],
    [for policy in google_monitoring_alert_policy.pubsub_backlog : policy.display_name],
    [for policy in google_monitoring_alert_policy.pubsub_message_age : policy.display_name],
    [google_monitoring_alert_policy.cloud_sql_cpu.display_name],
  )
}

output "logging_metric_name" {
  description = "User-defined metric counting error-level logs from Alex Cloud Run services."
  value       = google_logging_metric.cloud_run_errors.name
}
