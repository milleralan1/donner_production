data "google_project" "current" {
  project_id = var.project_id
}

locals {
  name_prefix = var.resource_suffix != "" ? "${var.project_name}-${var.environment}-${var.resource_suffix}" : "${var.project_name}-${var.environment}"

  common_labels = {
    project     = var.project_name
    environment = var.environment
    managed_by  = "terraform"
  }
}

# Enable required APIs
resource "google_project_service" "run" {
  service            = "run.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "cloudbuild" {
  service            = "cloudbuild.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "artifactregistry" {
  service            = "artifactregistry.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "aiplatform" {
  service            = "aiplatform.googleapis.com"
  disable_on_destroy = false
}

# Cloud Storage bucket for conversation memory
resource "google_storage_bucket" "memory" {
  name                        = "${local.name_prefix}-memory-${data.google_project.current.number}"
  location                    = var.region
  uniform_bucket_level_access = true

  # Lets `terraform destroy` remove the bucket even if it still has
  # objects in it - no manual "empty the bucket first" step needed.
  force_destroy = true

  labels = local.common_labels
}

# Service account the backend runs as
resource "google_service_account" "runtime" {
  account_id   = "${local.name_prefix}-runtime"
  display_name = "Digital Twin Runtime (${var.environment})"
}

resource "google_project_iam_member" "runtime_storage" {
  project = var.project_id
  role    = "roles/storage.objectAdmin"
  member  = "serviceAccount:${google_service_account.runtime.email}"
}

resource "google_project_iam_member" "runtime_vertex" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.runtime.email}"
}

# Artifact Registry repository to hold the backend container image
resource "google_artifact_registry_repository" "repo" {
  location      = var.region
  repository_id = "${local.name_prefix}-repo"
  format        = "DOCKER"
  labels        = local.common_labels

  depends_on = [google_project_service.artifactregistry]
}

# Build and push the backend container image with Cloud Build.
# Terraform doesn't build containers itself, so we shell out to
# `gcloud builds submit` via a local-exec provisioner.
resource "null_resource" "build_and_push" {
  triggers = {
    # Rebuild whenever the backend source changes
    source_hash = sha1(join("", [
      for f in fileset("${path.module}/../backend", "**") :
      filesha1("${path.module}/../backend/${f}")
    ]))
  }

  provisioner "local-exec" {
    command = "gcloud builds submit ${path.module}/../backend --project=${var.project_id} --tag=${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.repo.repository_id}/${var.project_name}-api:latest"
  }

  depends_on = [google_artifact_registry_repository.repo, google_project_service.cloudbuild]
}

# Cloud Run service
resource "google_cloud_run_v2_service" "api" {
  name     = "${local.name_prefix}-api"
  location = var.region
  labels   = local.common_labels

  template {
    service_account = google_service_account.runtime.email
    timeout         = "${var.cloud_run_timeout}s"

    scaling {
      min_instance_count = var.cloud_run_min_instances
      max_instance_count = var.cloud_run_max_instances
    }

    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.repo.repository_id}/${var.project_name}-api:latest"

      env {
        name  = "USE_GCS"
        value = "true"
      }
      env {
        name  = "GCS_BUCKET"
        value = google_storage_bucket.memory.name
      }
      env {
        name  = "GEMINI_MODEL_ID"
        value = var.gemini_model_id
      }
      env {
        name  = "GCP_PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "GCP_REGION"
        value = var.region
      }
      env {
        name  = "CORS_ORIGINS"
        value = var.cors_origins
      }
    }
  }

  depends_on = [null_resource.build_and_push, google_project_service.run]
}

# Allow public (unauthenticated) access, equivalent to API Gateway's public route
resource "google_cloud_run_v2_service_iam_member" "public" {
  name     = google_cloud_run_v2_service.api.name
  location = google_cloud_run_v2_service.api.location
  project  = var.project_id
  role     = "roles/run.invoker"
  member   = "allUsers"
}
