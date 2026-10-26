variable "project_id" {
  description = "Google Cloud project that hosts the agent services."
  type        = string
}

variable "region" {
  description = "Region for Artifact Registry, Cloud Run, and Pub/Sub push delivery."
  type        = string
}

variable "artifact_repository_id" {
  description = "Artifact Registry Docker repository ID."
  type        = string
  default     = "alex-agents"
}

variable "agent_image_urls" {
  description = "Container image URL for each role, pushed before applying Cloud Run services."
  type        = map(string)

  validation {
    condition = alltrue([
      for role in ["planner", "tagger", "reporter", "charter", "retirement"] :
      startswith(try(var.agent_image_urls[role], ""), "${var.region}-docker.pkg.dev/${var.project_id}/")
    ])
    error_message = "Provide a regional Artifact Registry image URL for all five agent roles."
  }
}

variable "agent_service_account_email" {
  description = "Existing shared alex-agents service account created for Guide 5."
  type        = string
}

variable "api_service_account_email" {
  description = "Existing alex-api service account that publishes analysis jobs."
  type        = string
}

variable "groq_model" {
  description = "LiteLLM Groq model name supporting the agent tool calls."
  type        = string
  default     = "groq/llama-3.3-70b-versatile"

  validation {
    condition     = startswith(var.groq_model, "groq/")
    error_message = "groq_model must use the groq/ LiteLLM prefix."
  }
}

variable "groq_api_key_secret_id" {
  description = "Secret Manager secret ID containing the Groq API key."
  type        = string
  default     = "alex-groq-api-key"
}

variable "database_connection_name" {
  description = "Cloud SQL instance connection name from the Guide 5 Terraform output."
  type        = string
}

variable "database_name" {
  description = "Cloud SQL application database."
  type        = string
  default     = "alex"
}

variable "database_user" {
  description = "Least-privilege Cloud SQL application user."
  type        = string
  default     = "alex_app"
}

variable "database_password_secret_id" {
  description = "Secret Manager secret ID created by the Guide 5 Terraform stack."
  type        = string
  default     = "alex-cloud-sql-password"
}

variable "massive_api_key_secret_id" {
  description = "Optional Secret Manager secret ID containing the Massive API key."
  type        = string
  default     = null
  nullable    = true
}

variable "ingestion_service_name" {
  description = "Cloud Run ingestion service name from Guide 3."
  type        = string
  default     = "alex-ingestion"
}

variable "ingestion_service_region" {
  description = "Region of the Cloud Run ingestion service."
  type        = string
}

variable "ingestion_service_url" {
  description = "HTTPS base URL of the private Cloud Run ingestion service."
  type        = string
}

variable "ingestion_service_audience" {
  description = "Optional ID-token audience for the ingestion service; defaults to its URL."
  type        = string
  default     = null
  nullable    = true
}

variable "max_instances" {
  description = "Maximum instances for each agent service."
  type        = number
  default     = 3

  validation {
    condition     = var.max_instances >= 1
    error_message = "max_instances must be at least 1."
  }
}

variable "dead_letter_max_delivery_attempts" {
  description = "Number of failed Pub/Sub delivery attempts before dead-letter routing."
  type        = number
  default     = 20

  validation {
    condition     = var.dead_letter_max_delivery_attempts >= 5 && var.dead_letter_max_delivery_attempts <= 100
    error_message = "Pub/Sub dead-letter delivery attempts must be between 5 and 100."
  }
}
