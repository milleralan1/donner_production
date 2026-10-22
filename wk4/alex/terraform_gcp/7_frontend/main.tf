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

resource "google_project_service" "required" {
  for_each = toset([
    "artifactregistry.googleapis.com",
    "iam.googleapis.com",
    "run.googleapis.com",
    "secretmanager.googleapis.com",
    "sqladmin.googleapis.com",
  ])

  project            = var.project_id
  service            = each.key
  disable_on_destroy = false
}

data "google_service_account" "api" {
  account_id = split("@", var.api_service_account_email)[0]
  project    = var.project_id
}

resource "google_artifact_registry_repository" "app" {
  location      = var.region
  repository_id = var.artifact_repository_id
  description   = "Alex GCP API and frontend images"
  format        = "DOCKER"

  depends_on = [google_project_service.required]
}

resource "google_service_account" "frontend" {
  account_id   = "alex-frontend"
  display_name = "Alex Next.js frontend runtime"

  depends_on = [google_project_service.required]
}

resource "google_secret_manager_secret_iam_member" "clerk_secret" {
  project   = var.project_id
  secret_id = var.clerk_secret_key_secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.frontend.email}"
}

resource "google_cloud_run_v2_service" "api" {
  name                = "alex-api"
  location            = var.region
  deletion_protection = false
  ingress             = "INGRESS_TRAFFIC_ALL"

  template {
    service_account                  = data.google_service_account.api.email
    timeout                          = "300s"
    max_instance_request_concurrency = 40

    scaling {
      max_instance_count = var.max_instances
    }

    containers {
      image = var.api_image_url

      ports {
        container_port = 8080
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "1Gi"
        }
      }

      env {
        name  = "DATABASE_BACKEND"
        value = "cloud_sql"
      }

      env {
        name  = "CLOUD_SQL_CONNECTION_NAME"
        value = var.database_connection_name
      }

      env {
        name  = "CLOUD_SQL_IP_TYPE"
        value = "PUBLIC"
      }

      env {
        name  = "DB_NAME"
        value = var.database_name
      }

      env {
        name  = "DB_USER"
        value = var.database_user
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
        name  = "ALEX_QUEUE_PROVIDER"
        value = "pubsub"
      }

      env {
        name  = "PUBSUB_TOPIC"
        value = "projects/${var.project_id}/topics/${var.pubsub_topic_id}"
      }

      env {
        name  = "CLERK_JWKS_URL"
        value = var.clerk_jwks_url
      }

      env {
        name  = "CLERK_ISSUER"
        value = var.clerk_issuer
      }

      env {
        name  = "CORS_ORIGINS"
        value = var.frontend_origin
      }
    }
  }

  depends_on = [
    google_project_service.required,
  ]
}

resource "google_cloud_run_v2_service_iam_member" "api_public" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.api.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_cloud_run_v2_service" "frontend" {
  name                = "alex-frontend"
  location            = var.region
  deletion_protection = false
  ingress             = "INGRESS_TRAFFIC_ALL"

  template {
    service_account                  = google_service_account.frontend.email
    timeout                          = "300s"
    max_instance_request_concurrency = 80

    scaling {
      max_instance_count = var.max_instances
    }

    containers {
      image = var.frontend_image_url

      ports {
        container_port = 8080
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "1Gi"
        }
      }

      env {
        name = "CLERK_SECRET_KEY"
        value_source {
          secret_key_ref {
            secret  = var.clerk_secret_key_secret_id
            version = "latest"
          }
        }
      }

      env {
        name  = "NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY"
        value = var.clerk_publishable_key
      }
    }
  }

  depends_on = [
    google_project_service.required,
    google_secret_manager_secret_iam_member.clerk_secret,
  ]
}

resource "google_cloud_run_v2_service_iam_member" "frontend_public" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.frontend.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
