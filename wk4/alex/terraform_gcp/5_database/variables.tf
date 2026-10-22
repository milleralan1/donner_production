variable "project_id" {
  description = "Google Cloud project that owns the Cloud SQL instance."
  type        = string
}

variable "region" {
  description = "Region for the Cloud SQL instance."
  type        = string
}

variable "instance_name" {
  description = "Cloud SQL instance name."
  type        = string
  default     = "alex-postgres"
}

variable "database_version" {
  description = "Cloud SQL PostgreSQL version."
  type        = string
  default     = "POSTGRES_16"
}

variable "tier" {
  description = "Cloud SQL machine tier; choose for the region and budget."
  type        = string
  default     = "db-custom-1-3840"
}

variable "disk_size_gb" {
  description = "Initial SSD size in GB."
  type        = number
  default     = 10

  validation {
    condition     = var.disk_size_gb >= 10
    error_message = "disk_size_gb must be at least 10."
  }
}

variable "database_name" {
  description = "Application database name."
  type        = string
  default     = "alex"
}

variable "database_user" {
  description = "Least-privilege application database user name."
  type        = string
  default     = "alex_app"
}

variable "password_secret_id" {
  description = "Secret Manager secret ID where Terraform stores the generated password."
  type        = string
  default     = "alex-cloud-sql-password"
}

variable "runtime_service_accounts" {
  description = "Emails of the Cloud Run service accounts allowed to connect and read the DB password."
  type        = set(string)
}

variable "enable_public_ip" {
  description = "Enable public IP for Cloud SQL Connector connectivity."
  type        = bool
  default     = true
}

variable "private_network" {
  description = "Optional full VPC network resource name for private IP."
  type        = string
  default     = null
  nullable    = true
}

variable "authorized_networks" {
  description = "Optional authorized networks for direct connections. Prefer the Cloud SQL connector."
  type = list(object({
    name = string
    cidr = string
  }))
  default = []
}

variable "deletion_protection" {
  description = "Protect the database instance from accidental Terraform deletion."
  type        = bool
  default     = true
}
