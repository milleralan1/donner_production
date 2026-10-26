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

moved {
  from = google_secret_manager_secret_iam_member.polygon_api_key
  to   = google_secret_manager_secret_iam_member.massive_api_key
}

locals {
  agent_roles = toset(["planner", "tagger", "reporter", "charter", "retirement"])
  common_env = {
    ALEX_LLM_PROVIDER         = "groq"
    GROQ_MODEL                = var.groq_model
    DATABASE_BACKEND          = "cloud_sql"
    CLOUD_SQL_CONNECTION_NAME = var.database_connection_name
    CLOUD_SQL_IP_TYPE         = "PUBLIC"
    DB_NAME                   = var.database_name
    DB_USER                   = var.database_user
    GOOGLE_CLOUD_PROJECT      = var.project_id
    GOOGLE_CLOUD_LOCATION     = var.region
    MOCK_LAMBDAS              = "false"
    PORT                      = "8080"
  }
}

resource "google_project_service" "required" {
  for_each = toset([
    "artifactregistry.googleapis.com",
    "iamcredentials.googleapis.com",
    "pubsub.googleapis.com",
    "run.googleapis.com",
    "secretmanager.googleapis.com",
    "sqladmin.googleapis.com",
  ])

  project            = var.project_id
  service            = each.key
  disable_on_destroy = false
}

data "google_project" "current" {
  project_id = var.project_id
}

data "google_service_account" "agents" {
  account_id = split("@", var.agent_service_account_email)[0]
  project    = var.project_id
}

data "google_service_account" "api" {
  account_id = split("@", var.api_service_account_email)[0]
  project    = var.project_id
}

resource "google_artifact_registry_repository" "agents" {
  location      = var.region
  repository_id = var.artifact_repository_id
  description   = "Alex GCP agent service images"
  format        = "DOCKER"

  depends_on = [google_project_service.required]
}

resource "google_secret_manager_secret_iam_member" "groq_api_key" {
  project   = var.project_id
  secret_id = var.groq_api_key_secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${data.google_service_account.agents.email}"

  depends_on = [google_project_service.required]
}

resource "google_secret_manager_secret_iam_member" "massive_api_key" {
  count     = var.massive_api_key_secret_id == null ? 0 : 1
  project   = var.project_id
  secret_id = var.massive_api_key_secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${data.google_service_account.agents.email}"
}

resource "google_service_account" "pubsub_push" {
  account_id   = "alex-pubsub-push"
  display_name = "Alex Pub/Sub push identity"

  depends_on = [google_project_service.required]
}

resource "google_cloud_run_v2_service" "agent" {
  for_each = local.agent_roles

  name                = "alex-${each.key}"
  location            = var.region
  deletion_protection = false
  ingress             = "INGRESS_TRAFFIC_ALL"

  template {
    service_account                  = data.google_service_account.agents.email
    timeout                          = each.key == "planner" ? "3600s" : "900s"
    max_instance_request_concurrency = each.key == "planner" ? 1 : 4

    scaling {
      max_instance_count = var.max_instances
    }

    containers {
      image = var.agent_image_urls[each.key]

      ports {
        container_port = 8080
      }

      resources {
        limits = {
          cpu    = each.key == "planner" ? "2" : "1"
          memory = "2Gi"
        }
      }

      dynamic "env" {
        for_each = local.common_env
        content {
          name  = env.key
          value = env.value
        }
      }

      env {
        name  = "ALEX_AGENT_ROLE"
        value = each.key
      }

      env {
        name = "DB_PASSWORD"
        value_source {
          secret_key_ref {
            secret  = var.database_password_secret_id
            version = "latest"
          }
        }
      }

      env {
        name = "GROQ_API_KEY"
        value_source {
          secret_key_ref {
            secret  = var.groq_api_key_secret_id
            version = "latest"
          }
        }
      }

      dynamic "env" {
        for_each = each.key == "planner" ? {
          TAGGER_SERVICE_URL     = google_cloud_run_v2_service.agent["tagger"].uri
          REPORTER_SERVICE_URL   = google_cloud_run_v2_service.agent["reporter"].uri
          CHARTER_SERVICE_URL    = google_cloud_run_v2_service.agent["charter"].uri
          RETIREMENT_SERVICE_URL = google_cloud_run_v2_service.agent["retirement"].uri
        } : {}
        content {
          name  = env.key
          value = env.value
        }
      }

      dynamic "env" {
        for_each = each.key == "reporter" ? {
          ALEX_INGESTION_URL = var.ingestion_service_url
        } : {}
        content {
          name  = env.key
          value = env.value
        }
      }

      dynamic "env" {
        for_each = each.key == "reporter" && var.ingestion_service_audience != null ? {
          ALEX_INGESTION_AUDIENCE = var.ingestion_service_audience
        } : {}
        content {
          name  = env.key
          value = env.value
        }
      }

      dynamic "env" {
        for_each = each.key == "planner" && var.massive_api_key_secret_id != null ? [var.massive_api_key_secret_id] : []
        content {
          name = "MASSIVE_API_KEY"
          value_source {
            secret_key_ref {
              secret  = env.value
              version = "latest"
            }
          }
        }
      }

      startup_probe {
        initial_delay_seconds = 10
        timeout_seconds       = 3
        period_seconds        = 10
        failure_threshold     = 12

        http_get {
          path = "/healthz"
        }
      }
    }
  }

  depends_on = [
    google_project_service.required,
    google_secret_manager_secret_iam_member.groq_api_key,
  ]
}

resource "google_cloud_run_v2_service_iam_member" "agent_invoker" {
  for_each = local.agent_roles

  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.agent[each.key].name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${data.google_service_account.agents.email}"
}

resource "google_cloud_run_v2_service_iam_member" "ingestion_invoker" {
  project  = var.project_id
  location = var.ingestion_service_region
  name     = var.ingestion_service_name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${data.google_service_account.agents.email}"
}

resource "google_cloud_run_v2_service_iam_member" "pubsub_planner_invoker" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.agent["planner"].name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.pubsub_push.email}"
}

resource "google_service_account_iam_member" "pubsub_token_creator" {
  service_account_id = google_service_account.pubsub_push.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "serviceAccount:service-${data.google_project.current.number}@gcp-sa-pubsub.iam.gserviceaccount.com"

  depends_on = [google_pubsub_topic.jobs]
}

resource "google_pubsub_topic" "jobs" {
  name       = "alex-analysis-jobs"
  project    = var.project_id
  depends_on = [google_project_service.required]
}

resource "google_pubsub_topic" "dead_letter" {
  name       = "alex-analysis-jobs-dlq"
  project    = var.project_id
  depends_on = [google_project_service.required]
}

resource "google_pubsub_subscription" "dead_letter" {
  name  = "alex-analysis-jobs-dlq-monitor"
  topic = google_pubsub_topic.dead_letter.id
}

resource "google_pubsub_topic_iam_member" "dead_letter_publisher" {
  project = var.project_id
  topic   = google_pubsub_topic.dead_letter.name
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:service-${data.google_project.current.number}@gcp-sa-pubsub.iam.gserviceaccount.com"

  depends_on = [google_pubsub_topic.dead_letter]
}

resource "google_pubsub_topic_iam_member" "api_publisher" {
  project = var.project_id
  topic   = google_pubsub_topic.jobs.name
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:${data.google_service_account.api.email}"
}

resource "google_pubsub_subscription" "jobs" {
  name                       = "alex-analysis-jobs-planner"
  topic                      = google_pubsub_topic.jobs.id
  ack_deadline_seconds       = 600
  message_retention_duration = "604800s"

  push_config {
    push_endpoint = "${google_cloud_run_v2_service.agent["planner"].uri}/pubsub"

    oidc_token {
      service_account_email = google_service_account.pubsub_push.email
      audience              = google_cloud_run_v2_service.agent["planner"].uri
    }
  }

  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.dead_letter.id
    max_delivery_attempts = var.dead_letter_max_delivery_attempts
  }

  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "600s"
  }

  depends_on = [
    google_cloud_run_v2_service_iam_member.pubsub_planner_invoker,
    google_service_account_iam_member.pubsub_token_creator,
    google_pubsub_topic_iam_member.dead_letter_publisher,
  ]
}
