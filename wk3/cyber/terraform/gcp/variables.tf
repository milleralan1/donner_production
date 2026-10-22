variable "project_id" {
  description = "GCP Project ID"
  type        = string
}

variable "region" {
  description = "GCP region for Cloud Run deployment"
  type        = string
  default     = "us-central1"
}

variable "service_name" {
  description = "Name of the Cloud Run service"
  type        = string
  default     = "cyber-analyzer"
}

variable "openai_api_key" {
  description = "Gemini API key (passed to the OpenAI-compatible client)"
  type        = string
  sensitive   = true
  default     = ""
}

variable "openai_base_url" {
  description = "OpenAI-compatible API base URL"
  type        = string
  default     = ""
}

variable "openai_model" {
  description = "Model name used by the security analysis agent"
  type        = string
  default     = "gpt-4.1-mini"
}

variable "semgrep_app_token" {
  description = "Semgrep app token for security scanning"
  type        = string
  sensitive   = true
  default     = ""
}

variable "docker_image_tag" {
  description = "Tag for the Docker image"
  type        = string
  default     = "latest"
}

variable "docker_image_digest" {
  description = "Optional immutable Artifact Registry image digest, in sha256:<hex> format"
  type        = string
  default     = ""

  validation {
    condition     = var.docker_image_digest == "" || can(regex("^sha256:[0-9a-f]{64}$", var.docker_image_digest))
    error_message = "docker_image_digest must be empty or use sha256:<64 lowercase hexadecimal characters>."
  }
}

variable "allow_unauthenticated" {
  description = "Allow unauthenticated public access to the Cloud Run service"
  type        = bool
  default     = true
}
