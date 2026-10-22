terraform {
  required_version = ">= 1.5"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

resource "random_password" "database" {
  length           = 32
  special          = true
  override_special = "!#$%&*()-_=+[]{}<>:?"
}

resource "google_sql_database_instance" "alex" {
  name                = var.instance_name
  region              = var.region
  database_version    = var.database_version
  deletion_protection = var.deletion_protection

  settings {
    tier              = var.tier
    availability_type = "ZONAL"
    disk_type         = "PD_SSD"
    disk_size         = var.disk_size_gb
    disk_autoresize   = true

    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = false
    }

    ip_configuration {
      ipv4_enabled    = var.enable_public_ip
      private_network = var.private_network

      dynamic "authorized_networks" {
        for_each = var.authorized_networks
        content {
          name  = authorized_networks.value.name
          value = authorized_networks.value.cidr
        }
      }
    }

    user_labels = {
      application = "alex"
      managed_by  = "terraform"
    }
  }

  lifecycle {
    precondition {
      condition     = var.enable_public_ip || var.private_network != null
      error_message = "Set private_network when enable_public_ip is false."
    }
  }
}

resource "google_sql_database" "alex" {
  name     = var.database_name
  instance = google_sql_database_instance.alex.name
}

resource "google_sql_user" "application" {
  name     = var.database_user
  instance = google_sql_database_instance.alex.name
  password = random_password.database.result
}

resource "google_secret_manager_secret" "database_password" {
  secret_id = var.password_secret_id

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "database_password" {
  secret      = google_secret_manager_secret.database_password.id
  secret_data = random_password.database.result
}

resource "google_project_iam_member" "cloud_sql_client" {
  for_each = var.runtime_service_accounts

  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${each.value}"
}

resource "google_secret_manager_secret_iam_member" "database_password_accessor" {
  for_each = var.runtime_service_accounts

  secret_id = google_secret_manager_secret.database_password.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${each.value}"
}
