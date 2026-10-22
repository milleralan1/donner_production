terraform {
  required_version = ">= 1.5"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

locals {
  cloud_run_filter = join(" OR ", [
    for service in var.cloud_run_services :
    "resource.labels.service_name=\"${service}\""
  ])

  dashboard_widgets = [
    {
      title   = "Cloud Run request count"
      filter  = "resource.type=\"cloud_run_revision\" AND metric.type=\"run.googleapis.com/request_count\" AND (${local.cloud_run_filter})"
      aligner = "ALIGN_SUM"
      unit    = "requests"
    },
    {
      title   = "Cloud Run p95 request latency"
      filter  = "resource.type=\"cloud_run_revision\" AND metric.type=\"run.googleapis.com/request_latencies\" AND (${local.cloud_run_filter})"
      aligner = "ALIGN_PERCENTILE_95"
      unit    = "ms"
    },
    {
      title   = "Cloud Run error logs"
      filter  = "resource.type=\"cloud_run_revision\" AND metric.type=\"logging.googleapis.com/user/alex_cloud_run_error_logs\""
      aligner = "ALIGN_SUM"
      unit    = "errors"
    },
    {
      title   = "Pub/Sub undelivered messages"
      filter  = "resource.type=\"pubsub_subscription\" AND metric.type=\"pubsub.googleapis.com/subscription/num_undelivered_messages\""
      aligner = "ALIGN_MAX"
      unit    = "messages"
    },
    {
      title   = "Pub/Sub oldest unacked message age"
      filter  = "resource.type=\"pubsub_subscription\" AND metric.type=\"pubsub.googleapis.com/subscription/oldest_unacked_message_age\""
      aligner = "ALIGN_MAX"
      unit    = "seconds"
    },
    {
      title   = "Cloud SQL CPU utilization"
      filter  = "resource.type=\"cloudsql_database\" AND metric.type=\"cloudsql.googleapis.com/database/cpu/utilization\" AND resource.labels.database_id=\"${var.cloud_sql_database_id}\""
      aligner = "ALIGN_MEAN"
      unit    = "ratio"
    },
  ]
}

resource "google_project_service" "required" {
  for_each = toset([
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    "serviceusage.googleapis.com",
  ])

  project            = var.project_id
  service            = each.key
  disable_on_destroy = false
}

resource "google_logging_metric" "cloud_run_errors" {
  project     = var.project_id
  name        = "alex_cloud_run_error_logs"
  description = "Count error and higher severity logs from Alex Cloud Run services."
  filter      = "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=~\"^alex-\" AND severity>=ERROR"

  metric_descriptor {
    metric_kind  = "DELTA"
    value_type   = "INT64"
    unit         = "1"
    display_name = "Alex Cloud Run error logs"

    labels {
      key         = "service_name"
      value_type  = "STRING"
      description = "Cloud Run service that emitted the log."
    }
  }

  label_extractors = {
    service_name = "EXTRACT(resource.labels.service_name)"
  }

  depends_on = [google_project_service.required]
}

resource "google_monitoring_alert_policy" "cloud_run_errors" {
  project               = var.project_id
  display_name          = "Alex Cloud Run error logs"
  combiner              = "OR"
  enabled               = true
  notification_channels = var.notification_channel_ids

  conditions {
    display_name = "Alex service emitted error logs"

    condition_threshold {
      filter          = "resource.type=\"cloud_run_revision\" AND metric.type=\"logging.googleapis.com/user/alex_cloud_run_error_logs\""
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      duration        = "300s"

      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_SUM"
      }

      trigger {
        count = 1
      }
    }
  }

  documentation {
    content   = "Inspect Cloud Logging for the affected Alex service. Do not include credentials or financial records in alert annotations."
    mime_type = "text/markdown"
  }

  depends_on = [google_project_service.required, google_logging_metric.cloud_run_errors]
}

resource "google_monitoring_alert_policy" "pubsub_backlog" {
  for_each = toset(var.pubsub_subscription_ids)

  project               = var.project_id
  display_name          = "Alex Pub/Sub backlog: ${each.key}"
  combiner              = "OR"
  enabled               = true
  notification_channels = var.notification_channel_ids

  conditions {
    display_name = "Undelivered messages exceed ${var.pubsub_backlog_threshold}"

    condition_threshold {
      filter          = "resource.type=\"pubsub_subscription\" AND metric.type=\"pubsub.googleapis.com/subscription/num_undelivered_messages\" AND resource.labels.subscription_id=\"${each.key}\""
      comparison      = "COMPARISON_GT"
      threshold_value = var.pubsub_backlog_threshold
      duration        = "300s"

      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_MAX"
      }
    }
  }

  documentation {
    content   = "Check Planner health, Pub/Sub delivery, and the dead-letter subscription. Avoid replaying messages until the underlying failure is understood."
    mime_type = "text/markdown"
  }

  depends_on = [google_project_service.required]
}

resource "google_monitoring_alert_policy" "pubsub_message_age" {
  project               = var.project_id
  display_name          = "Alex Pub/Sub message age: ${each.key}"
  combiner              = "OR"
  enabled               = true
  notification_channels = var.notification_channel_ids

  for_each = toset(var.pubsub_subscription_ids)

  conditions {
    display_name = "Oldest unacked message exceeds ${var.pubsub_oldest_message_age_seconds}s"

    condition_threshold {
      filter          = "resource.type=\"pubsub_subscription\" AND metric.type=\"pubsub.googleapis.com/subscription/oldest_unacked_message_age\" AND resource.labels.subscription_id=\"${each.key}\""
      comparison      = "COMPARISON_GT"
      threshold_value = var.pubsub_oldest_message_age_seconds
      duration        = "300s"

      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_MAX"
      }
    }
  }

  documentation {
    content   = "Inspect the subscription delivery rate, Planner logs, and dead-letter routing before changing retry policy."
    mime_type = "text/markdown"
  }

  depends_on = [google_project_service.required]
}

resource "google_monitoring_alert_policy" "cloud_sql_cpu" {
  project               = var.project_id
  display_name          = "Alex Cloud SQL high CPU"
  combiner              = "OR"
  enabled               = true
  notification_channels = var.notification_channel_ids

  conditions {
    display_name = "Cloud SQL CPU utilization exceeds ${var.cloud_sql_cpu_threshold}"

    condition_threshold {
      filter          = "resource.type=\"cloudsql_database\" AND metric.type=\"cloudsql.googleapis.com/database/cpu/utilization\" AND resource.labels.database_id=\"${var.cloud_sql_database_id}\""
      comparison      = "COMPARISON_GT"
      threshold_value = var.cloud_sql_cpu_threshold
      duration        = "600s"

      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_MEAN"
      }
    }
  }

  documentation {
    content   = "Review Cloud SQL CPU, connection count, query load, and Cloud Run concurrency before increasing database capacity."
    mime_type = "text/markdown"
  }

  depends_on = [google_project_service.required]
}

resource "google_monitoring_dashboard" "alex" {
  project = var.project_id
  dashboard_json = jsonencode({
    displayName = "Alex service health"
    gridLayout = {
      columns = 2
      widgets = [
        for widget in local.dashboard_widgets : {
          title = widget.title
          xyChart = {
            dataSets = [{
              timeSeriesQuery = {
                timeSeriesFilter = {
                  filter = widget.filter
                  aggregation = {
                    alignmentPeriod  = "300s"
                    perSeriesAligner = widget.aligner
                  }
                }
              }
              plotType = "LINE"
            }]
            yAxis = {
              label = widget.unit
              scale = "LINEAR"
            }
          }
        }
      ]
    }
  })

  depends_on = [google_project_service.required, google_logging_metric.cloud_run_errors]
}
