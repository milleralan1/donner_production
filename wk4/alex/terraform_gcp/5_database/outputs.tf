output "instance_connection_name" {
  description = "Cloud SQL instance connection name for CLOUD_SQL_CONNECTION_NAME."
  value       = google_sql_database_instance.alex.connection_name
}

output "database_name" {
  description = "PostgreSQL database name."
  value       = google_sql_database.alex.name
}

output "database_user" {
  description = "Application PostgreSQL username."
  value       = google_sql_user.application.name
}

output "database_password_secret_id" {
  description = "Secret Manager secret ID containing the generated database password."
  value       = google_secret_manager_secret.database_password.secret_id
}

output "runtime_service_accounts" {
  description = "Runtime service accounts granted Cloud SQL and password-secret access."
  value       = var.runtime_service_accounts
}
