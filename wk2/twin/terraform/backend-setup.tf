# This file creates the Cloud Storage bucket for Terraform state
# Run this once per GCP project, then remove the file

resource "google_storage_bucket" "terraform_state" {
  name                        = "${var.project_name}-terraform-state-${data.google_project.current.number}"
  location                    = var.region
  uniform_bucket_level_access = true

  versioning {
    enabled = true
  }

  # Never force-destroy the state bucket - it's the source of truth
  # for every environment's infrastructure.
  force_destroy = false

  labels = {
    name        = "terraform-state-store"
    environment = "global"
    managed_by  = "terraform"
  }
}

# Note: data.google_project.current is already defined in main.tf

output "state_bucket_name" {
  value = google_storage_bucket.terraform_state.name
}
