variable "project_id" {
  description = "Google Cloud project that hosts the application."
  type        = string
}

variable "region" {
  description = "Region for the Cloud Run application services and Artifact Registry."
  type        = string
}

variable "artifact_repository_id" {
  description = "Artifact Registry Docker repository ID for the API and frontend."
  type        = string
  default     = "alex-app"
}

variable "api_image_url" {
  description = "GCP API container image, pushed before deploying the API service."
  type        = string
}

variable "frontend_image_url" {
  description = "Next.js standalone container image, pushed before deploying the frontend."
  type        = string
}

variable "api_service_account_email" {
  description = "Existing alex-api service account created in Guide 5."
  type        = string
}

variable "database_connection_name" {
  description = "Cloud SQL connection name from the Guide 5 Terraform output."
  type        = string
}

variable "database_name" {
  description = "Cloud SQL application database name."
  type        = string
  default     = "alex"
}

variable "database_user" {
  description = "Least-privilege application database user."
  type        = string
  default     = "alex_app"
}

variable "database_password_secret_id" {
  description = "Secret Manager secret ID for the Cloud SQL application password."
  type        = string
  default     = "alex-cloud-sql-password"
}

variable "pubsub_topic_id" {
  description = "Pub/Sub jobs topic created by the Guide 6 stack."
  type        = string
  default     = "alex-analysis-jobs"
}

variable "clerk_jwks_url" {
  description = "Clerk JWKS endpoint used to verify user JWT signatures."
  type        = string
}

variable "clerk_issuer" {
  description = "Exact Clerk JWT issuer URL, without a trailing slash."
  type        = string
}

variable "clerk_publishable_key" {
  description = "Clerk publishable key; this value is intentionally public."
  type        = string
}

variable "clerk_secret_key_secret_id" {
  description = "Secret Manager secret ID containing the Clerk server secret key."
  type        = string
  default     = "alex-clerk-secret-key"
}

variable "frontend_origin" {
  description = "Optional exact HTTPS frontend origin allowed by API CORS; set after first frontend deployment."
  type        = string
  default     = ""
}

variable "max_instances" {
  description = "Maximum instances for the API and frontend Cloud Run services."
  type        = number
  default     = 3

  validation {
    condition     = var.max_instances >= 1
    error_message = "max_instances must be at least 1."
  }
}
