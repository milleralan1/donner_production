variable "project_id" {
  description = "Google Cloud project that hosts Alex."
  type        = string
}

variable "region" {
  description = "Primary application region; used for provider defaults and links."
  type        = string
}

variable "cloud_run_services" {
  description = "Cloud Run service names included in request and latency charts."
  type        = set(string)
  default = [
    "alex-api",
    "alex-frontend",
    "alex-planner",
    "alex-tagger",
    "alex-reporter",
    "alex-charter",
    "alex-retirement",
    "alex-researcher",
    "alex-ingestion",
  ]

  validation {
    condition = length(var.cloud_run_services) > 0 && alltrue([
      for service in var.cloud_run_services : can(regex("^alex-[a-z0-9-]+$", service))
    ])
    error_message = "cloud_run_services must contain valid Alex Cloud Run service names."
  }
}

variable "pubsub_subscription_ids" {
  description = "Pub/Sub subscription IDs to monitor, including the Planner and dead-letter subscriptions."
  type        = set(string)
  default = [
    "alex-analysis-jobs-planner",
    "alex-analysis-jobs-dlq-monitor",
  ]

  validation {
    condition = length(var.pubsub_subscription_ids) > 0 && alltrue([
      for subscription in var.pubsub_subscription_ids :
      can(regex("^[a-z][a-z0-9_-]{2,254}$", subscription))
    ])
    error_message = "pubsub_subscription_ids must contain valid Pub/Sub subscription IDs."
  }
}

variable "cloud_sql_database_id" {
  description = "Cloud SQL Monitoring resource database_id, formatted as PROJECT_ID:INSTANCE_ID."
  type        = string
}

variable "notification_channel_ids" {
  description = "Existing Cloud Monitoring notification channel resource names; empty disables email or webhook delivery."
  type        = list(string)
  default     = []

  validation {
    condition = alltrue([
      for channel in var.notification_channel_ids :
      can(regex("^projects/[^/]+/notificationChannels/[^/]+$", channel))
    ])
    error_message = "Each notification channel must be a full Monitoring resource name."
  }
}

variable "pubsub_backlog_threshold" {
  description = "Alert when undelivered messages exceed this count for five minutes."
  type        = number
  default     = 100

  validation {
    condition     = var.pubsub_backlog_threshold >= 1
    error_message = "pubsub_backlog_threshold must be at least 1."
  }
}

variable "pubsub_oldest_message_age_seconds" {
  description = "Alert when an unacknowledged message exceeds this age in seconds."
  type        = number
  default     = 900

  validation {
    condition     = var.pubsub_oldest_message_age_seconds >= 60
    error_message = "pubsub_oldest_message_age_seconds must be at least 60."
  }
}

variable "cloud_sql_cpu_threshold" {
  description = "Cloud SQL CPU utilization ratio that triggers an alert."
  type        = number
  default     = 0.8

  validation {
    condition     = var.cloud_sql_cpu_threshold > 0 && var.cloud_sql_cpu_threshold <= 1
    error_message = "cloud_sql_cpu_threshold must be greater than 0 and at most 1."
  }
}
