# Day 4: Infrastructure as Code with Terraform

## From Manual to Automated Deployment

Welcome to Day 4! Today marks a significant shift in how we deploy our Digital Twin. We're moving from manual `gcloud`/Console operations to Infrastructure as Code (IaC) using Terraform. This transformation brings version control, repeatability, and the ability to deploy multiple environments with a single command. By the end of today, you'll be managing dev, test, and production environments like a professional DevOps engineer!

## What You'll Learn Today

- **Terraform fundamentals** - Infrastructure as Code concepts
- **State management** - How Terraform tracks your resources
- **Workspaces** - Managing multiple environments
- **Automated deployment** - One-command infrastructure provisioning
- **Environment isolation** - Separate dev, test, and production
- **Optional: Custom domains** - Professional DNS configuration via Firebase Hosting

## Part 1: Clean Slate - Remove Manual Resources

Before we embrace automation, let's clean up all the resources we created manually on Days 2 and 3. This final manual cleanup will help reinforce what Terraform will manage for us.

### Step 1: Delete the Cloud Run Service

```bash
gcloud run services delete twin-api --region us-central1
```

### Step 2: Delete the Cloud Storage Memory Bucket

```bash
gcloud storage rm -r gs://twin-memory-your-suffix
```

### Step 3: Remove the Artifact Registry Image (if you built one manually)

```bash
gcloud artifacts repositories delete twin-repo --location us-central1
```

### Step 4: Delete the Service Account

```bash
gcloud iam service-accounts delete twin-runtime@YOUR_PROJECT_ID.iam.gserviceaccount.com
```

### Step 5: Clear the Firebase Hosting Site (Optional)

You can leave your Firebase Hosting site as-is (Terraform won't manage it — see the note in Part 5), or clear its content:

```bash
cd frontend
firebase hosting:disable
```

### Step 6: Verify Clean State

```bash
gcloud run services list
gcloud storage buckets list
gcloud iam service-accounts list
```

None of these should show any `twin-` prefixed resources (aside from any default service accounts GCP creates automatically).

✅ **Checkpoint**: You now have a clean GCP project, ready for Terraform to manage everything!

## Part 2: Understanding Terraform

### What is Infrastructure as Code?

Infrastructure as Code (IaC) treats your infrastructure configuration as source code. Instead of running one-off `gcloud` commands, you define your infrastructure in text files that can be:
- **Version controlled** - Track changes over time
- **Reviewed** - Use pull requests for infrastructure changes
- **Automated** - Deploy with CI/CD pipelines
- **Repeatable** - Create identical environments

### Key Terraform Concepts

**1. Resources**: The building blocks - each GCP service you want to create
```hcl
resource "google_storage_bucket" "example" {
  name     = "my-bucket-name"
  location = "US"
}
```

**2. State**: Terraform's record of what it has created
- Stored in `terraform.tfstate` file
- Maps your configuration to real resources
- Critical for updates and deletions

**3. Providers**: Plugins that interact with cloud providers
```hcl
provider "google" {
  project = var.project_id
  region  = "us-central1"
}
```

**4. Variables**: Parameterize your configuration
```hcl
variable "environment" {
  description = "Environment name"
  type        = string
}
```

**5. Workspaces**: Separate state for different environments
- Each workspace has its own state file
- Perfect for dev/test/prod separation

### Step 1: Install Terraform

**Mac (using Homebrew):**
```bash
brew tap hashicorp/tap
brew install hashicorp/tap/terraform
```

**Mac/Linux (manual):**
1. Visit: https://developer.hashicorp.com/terraform/install
2. Download the appropriate package for your system
3. Extract and move to PATH:
```bash
# Example for Mac (adjust URL for your system)
curl -O https://releases.hashicorp.com/terraform/1.10.0/terraform_1.10.0_darwin_amd64.zip
unzip terraform_1.10.0_darwin_amd64.zip
sudo mv terraform /usr/local/bin/
```

**Windows:**
1. Visit: https://developer.hashicorp.com/terraform/install
2. Download the Windows package
3. Extract the .exe file
4. Add to your PATH:
   - Right-click "This PC" → Properties
   - Advanced system settings → Environment Variables
   - Edit PATH and add the Terraform directory

**Verify Installation:**
```bash
terraform --version
```

You should see something like: `Terraform v1.10.0` (version may vary)

### Step 2: Update .gitignore

Add Terraform-specific entries to your `.gitignore`:

```gitignore
# Terraform
*.tfstate
*.tfstate.*
.terraform/
.terraform.lock.hcl
terraform.tfstate.d/
*.tfvars
!terraform.tfvars
!prod.tfvars

# Environment files
.env
.env.*

# Node
node_modules/
out/
.next/

# Python
__pycache__/
*.pyc
.venv/
uv.lock

# IDE
.vscode/
.idea/
*.swp
.DS_Store
```

Note there's no "Lambda packages" entry to worry about here — Cloud Build builds your container image in the cloud, so there's nothing bulky left behind locally.

## Part 3: Create Terraform Configuration

### Step 1: Create Terraform Directory Structure

In Cursor's file explorer (the left sidebar):

1. Right-click in the file explorer in the blank space below all the files
2. Select **New Folder**
3. Name it `terraform`

Your project structure should now have:
```
twin/
├── backend/
├── frontend/
├── memory/
└── terraform/   (new)
```

### Step 2: Create Provider Configuration

Create `terraform/versions.tf`:

```hcl
terraform {
  required_version = ">= 1.0"

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
```

### Step 3: Define Variables

Create `terraform/variables.tf`:

```hcl
variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "project_name" {
  description = "Name prefix for all resources"
  type        = string
  validation {
    condition     = can(regex("^[a-z0-9-]+$", var.project_name))
    error_message = "Project name must contain only lowercase letters, numbers, and hyphens."
  }
}

variable "environment" {
  description = "Environment name (dev, test, prod)"
  type        = string
  validation {
    condition     = contains(["dev", "test", "prod"], var.environment)
    error_message = "Environment must be one of: dev, test, prod."
  }
}

variable "region" {
  description = "GCP region for resources"
  type        = string
  default     = "us-central1"
}

variable "gemini_model_id" {
  description = "Vertex AI Gemini model ID"
  type        = string
  default     = "gemini-2.5-flash-lite"
}

variable "cloud_run_timeout" {
  description = "Cloud Run request timeout in seconds"
  type        = number
  default     = 60
}

variable "cloud_run_min_instances" {
  description = "Minimum Cloud Run instances (0 = scale to zero)"
  type        = number
  default     = 0
}

variable "cloud_run_max_instances" {
  description = "Maximum Cloud Run instances"
  type        = number
  default     = 5
}

variable "cors_origins" {
  description = "Allowed CORS origin for the frontend"
  type        = string
  default     = "*"
}
```

### Step 4: Create Main Infrastructure

Create `terraform/main.tf`:

```hcl
data "google_project" "current" {
  project_id = var.project_id
}

locals {
  name_prefix = "${var.project_name}-${var.environment}"

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
    command = "gcloud builds submit ${path.module}/../backend --project=${var.project_id} --tag=${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.repo.repository_id}/twin-api:latest"
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
      image = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.repo.repository_id}/twin-api:latest"

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
```

> **Note on API Gateway**: as in Day 2, Cloud Run's own HTTPS endpoint replaces the separate "API Gateway" resource from the AWS version — there's no `google_api_gateway_*` resource in this configuration because it isn't needed.

> **Note on CloudFront/custom domains**: this configuration deliberately does **not** provision a Cloud Storage frontend bucket, load balancer, or managed SSL certificate the way the AWS version wired up S3 + CloudFront + ACM + Route 53. Firebase Hosting (Part 4 below) is deployed separately via the Firebase CLI and already includes global CDN and HTTPS — see Part 8 for how custom domains work there.

### Step 5: Define Outputs

Create `terraform/outputs.tf`:

```hcl
output "cloud_run_url" {
  description = "URL of the Cloud Run service"
  value       = google_cloud_run_v2_service.api.uri
}

output "gcs_memory_bucket" {
  description = "Name of the Cloud Storage bucket for memory storage"
  value       = google_storage_bucket.memory.name
}

output "service_account_email" {
  description = "Email of the runtime service account"
  value       = google_service_account.runtime.email
}

output "cloud_run_service_name" {
  description = "Name of the Cloud Run service"
  value       = google_cloud_run_v2_service.api.name
}
```

### Step 6: Create Default Variable Values

Create `terraform/terraform.tfvars`:

```hcl
project_id               = "your-gcp-project-id"
project_name             = "twin"
environment              = "dev"
region                   = "us-central1"
gemini_model_id          = "gemini-2.5-flash-lite"
cloud_run_timeout        = 60
cloud_run_min_instances  = 0
cloud_run_max_instances  = 5
cors_origins             = "*"
```

### Step 7: Update Frontend to Use Environment Variables

Before we create our deployment scripts, we need to update the frontend to use environment variables for the API URL instead of hardcoding it.

Update `frontend/components/twin.tsx` - find the fetch call (around line 43) and replace:

```typescript
// Find this line:
const response = await fetch('http://localhost:8000/chat', {

// Replace with:
const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/chat`, {
```

This change allows the frontend to:
- Use `http://localhost:8000` during local development
- Use the production Cloud Run URL (set via environment variable) when deployed

**Note**: Next.js requires environment variables accessible in the browser to be prefixed with `NEXT_PUBLIC_`.

## Part 4: Create Deployment Scripts

### Step 1: Create Scripts Directory

In Cursor's file explorer (the left sidebar):

1. Right-click in the File Explorer in the blank space under the files
2. Select **New Folder**
3. Name it `scripts`

### Step 2: Set Up a Firebase Hosting Site per Environment

Since we're managing `dev`, `test`, and `prod` as isolated environments, create a separate Firebase Hosting **site** for each one (a single Firebase project can host multiple independent sites):

```bash
firebase hosting:sites:create twin-dev
firebase hosting:sites:create twin-test
firebase hosting:sites:create twin-prod
```

Then, in `frontend/`, create `.firebaserc` mapping friendly target names to each site:

```bash
firebase target:apply hosting dev twin-dev
firebase target:apply hosting test twin-test
firebase target:apply hosting prod twin-prod
```

Update `frontend/firebase.json` to reference the target instead of a single default site:

```json
{
  "hosting": {
    "target": "dev",
    "public": "out",
    "ignoreIndex": false,
    "cleanUrls": true,
    "trailingSlash": false
  }
}
```

Deploying will now use `firebase deploy --only hosting:dev` (or `test` / `prod`), selecting the right site for the environment — this is what the scripts below do.

### Step 3: Create Shell Script for Mac/Linux

**Important**: All students (including Windows users) need to create this file, as it will be used by GitHub Actions on Day 5.

Create `scripts/deploy.sh`:

```bash
#!/bin/bash
set -e

ENVIRONMENT=${1:-dev}          # dev | test | prod
PROJECT_NAME=${2:-twin}

echo "🚀 Deploying ${PROJECT_NAME} to ${ENVIRONMENT}..."

# 1. Terraform workspace & apply
cd "$(dirname "$0")/../terraform"
terraform init -input=false

if ! terraform workspace list | grep -q "$ENVIRONMENT"; then
  terraform workspace new "$ENVIRONMENT"
else
  terraform workspace select "$ENVIRONMENT"
fi

# Use prod.tfvars for production environment
if [ "$ENVIRONMENT" = "prod" ]; then
  TF_APPLY_CMD=(terraform apply -var-file=prod.tfvars -var="project_name=$PROJECT_NAME" -var="environment=$ENVIRONMENT" -auto-approve)
else
  TF_APPLY_CMD=(terraform apply -var="project_name=$PROJECT_NAME" -var="environment=$ENVIRONMENT" -auto-approve)
fi

echo "🎯 Applying Terraform..."
"${TF_APPLY_CMD[@]}"

API_URL=$(terraform output -raw cloud_run_url)

# 2. Build + deploy frontend
cd ../frontend

# Create production environment file with API URL
echo "📝 Setting API URL for production..."
echo "NEXT_PUBLIC_API_URL=$API_URL" > .env.production

npm install
npm run build
firebase deploy --only "hosting:${ENVIRONMENT}"
cd ..

# 3. Final messages
HOSTING_URL=$(firebase hosting:sites:list --json 2>/dev/null | grep -A2 "\"twin-${ENVIRONMENT}\"" | grep defaultUrl | sed -E 's/.*"(https:[^"]+)".*/\1/' || echo "check 'firebase hosting:sites:list'")
echo -e "\n✅ Deployment complete!"
echo "🌐 Firebase Hosting URL : $HOSTING_URL"
echo "📡 Cloud Run URL        : $API_URL"
```

**For Mac/Linux users only** - make it executable:
```bash
chmod +x scripts/deploy.sh
```

**Windows users**: You don't need to run the chmod command, just create the file.

### Step 4: Create PowerShell Script for Windows

**Mac/Linux users**: You can skip this step - it's only needed for Windows users.

Create `scripts/deploy.ps1`:

```powershell
param(
    [string]$Environment = "dev",   # dev | test | prod
    [string]$ProjectName = "twin"
)
$ErrorActionPreference = "Stop"

Write-Host "Deploying $ProjectName to $Environment ..." -ForegroundColor Green

# 1. Terraform workspace & apply
Set-Location (Join-Path (Split-Path $PSScriptRoot -Parent) "terraform")
terraform init -input=false

if (-not (terraform workspace list | Select-String $Environment)) {
    terraform workspace new $Environment
} else {
    terraform workspace select $Environment
}

if ($Environment -eq "prod") {
    terraform apply -var-file="prod.tfvars" -var="project_name=$ProjectName" -var="environment=$Environment" -auto-approve
} else {
    terraform apply -var="project_name=$ProjectName" -var="environment=$Environment" -auto-approve
}

$ApiUrl = terraform output -raw cloud_run_url

# 2. Build + deploy frontend
Set-Location ..\frontend

Write-Host "Setting API URL for production..." -ForegroundColor Yellow
"NEXT_PUBLIC_API_URL=$ApiUrl" | Out-File .env.production -Encoding utf8

npm install
npm run build
firebase deploy --only "hosting:$Environment"
Set-Location ..

# 3. Final summary
Write-Host "Deployment complete!" -ForegroundColor Green
Write-Host "Cloud Run URL : $ApiUrl" -ForegroundColor Cyan
Write-Host "Check 'firebase hosting:sites:list' for the Hosting URL" -ForegroundColor Cyan
```

## Part 5: Deploy Development Environment

### Step 1: Initialize Terraform

```bash
cd terraform
terraform init
```

You should see:
```
Initializing the backend...
Initializing provider plugins...
- Installing hashicorp/google v6.x.x...
Terraform has been successfully initialized!
```

### Step 2: Deploy Using the Script

**Mac/Linux from the project root:**
```bash
./scripts/deploy.sh dev
```

**Windows (PowerShell) from the project root:**
```powershell
.\scripts\deploy.ps1 -Environment dev
```

The script will:
1. Create a `dev` workspace in Terraform
2. Deploy all infrastructure (this triggers a Cloud Build of your container image)
3. Build and deploy the frontend to the `twin-dev` Firebase Hosting site
4. Display the URLs

### Step 3: Test Your Development Environment

1. Visit the Firebase Hosting URL shown in the output (or run `firebase hosting:sites:list`)
2. Test the chat functionality
3. Verify everything works as before

✅ **Checkpoint**: Your dev environment is now deployed via Terraform!

## Part 6: Deploy Test Environment

Now let's deploy a completely separate test environment:

### Step 1: Deploy Test Environment

**Mac/Linux:**
```bash
./scripts/deploy.sh test
```

**Windows (PowerShell):**
```powershell
.\scripts\deploy.ps1 -Environment test
```

### Step 2: Verify Separate Resources

Check the GCP Console - you'll see separate resources for test:
- `twin-test-api` Cloud Run service
- `twin-test-memory-*` Cloud Storage bucket
- `twin-test-repo` Artifact Registry repository
- `twin-test-runtime` service account
- Separate `twin-test` Firebase Hosting site

### Step 3: Test Both Environments

1. Open the dev Hosting URL in one browser tab
2. Open the test Hosting URL in another tab
3. Have different conversations - they're completely isolated!

## Part 7: Destroying Infrastructure

Cleaning up on GCP is considerably simpler than on AWS. Because `google_storage_bucket.memory` is defined with `force_destroy = true`, Terraform can delete the bucket directly — there's no separate "empty the bucket first" step required.

### Step 1: Create Destroy Script for Mac/Linux

Create `scripts/destroy.sh`:

```bash
#!/bin/bash
set -e

if [ $# -eq 0 ]; then
    echo "❌ Error: Environment parameter is required"
    echo "Usage: $0 <environment>"
    echo "Example: $0 dev"
    echo "Available environments: dev, test, prod"
    exit 1
fi

ENVIRONMENT=$1
PROJECT_NAME=${2:-twin}

echo "🗑️ Preparing to destroy ${PROJECT_NAME}-${ENVIRONMENT} infrastructure..."

cd "$(dirname "$0")/../terraform"

if ! terraform workspace list | grep -q "$ENVIRONMENT"; then
    echo "❌ Error: Workspace '$ENVIRONMENT' does not exist"
    terraform workspace list
    exit 1
fi

terraform workspace select "$ENVIRONMENT"

echo "🔥 Running terraform destroy..."

if [ "$ENVIRONMENT" = "prod" ] && [ -f "prod.tfvars" ]; then
    terraform destroy -var-file=prod.tfvars -var="project_name=$PROJECT_NAME" -var="environment=$ENVIRONMENT" -auto-approve
else
    terraform destroy -var="project_name=$PROJECT_NAME" -var="environment=$ENVIRONMENT" -auto-approve
fi

echo "✅ Infrastructure for ${ENVIRONMENT} has been destroyed!"
echo ""
echo "💡 To also remove the Firebase Hosting site, run:"
echo "   firebase hosting:sites:delete ${PROJECT_NAME}-${ENVIRONMENT}"
echo ""
echo "💡 To remove the Terraform workspace completely, run:"
echo "   terraform workspace select default"
echo "   terraform workspace delete ${ENVIRONMENT}"
```

Make it executable:
```bash
chmod +x scripts/destroy.sh
```

### Step 2: Create Destroy Script for Windows

Create `scripts/destroy.ps1`:

```powershell
param(
    [Parameter(Mandatory=$true)]
    [string]$Environment,
    [string]$ProjectName = "twin"
)

if ($Environment -notmatch '^(dev|test|prod)$') {
    Write-Host "Error: Invalid environment '$Environment'" -ForegroundColor Red
    Write-Host "Available environments: dev, test, prod" -ForegroundColor Yellow
    exit 1
}

Write-Host "Preparing to destroy $ProjectName-$Environment infrastructure..." -ForegroundColor Yellow

Set-Location (Join-Path (Split-Path $PSScriptRoot -Parent) "terraform")

$workspaces = terraform workspace list
if (-not ($workspaces | Select-String $Environment)) {
    Write-Host "Error: Workspace '$Environment' does not exist" -ForegroundColor Red
    terraform workspace list
    exit 1
}

terraform workspace select $Environment

Write-Host "Running terraform destroy..." -ForegroundColor Yellow

if ($Environment -eq "prod" -and (Test-Path "prod.tfvars")) {
    terraform destroy -var-file="prod.tfvars" -var="project_name=$ProjectName" -var="environment=$Environment" -auto-approve
} else {
    terraform destroy -var="project_name=$ProjectName" -var="environment=$Environment" -auto-approve
}

Write-Host "Infrastructure for $Environment has been destroyed!" -ForegroundColor Green
Write-Host ""
Write-Host "  To also remove the Firebase Hosting site, run:" -ForegroundColor Cyan
Write-Host "   firebase hosting:sites:delete $ProjectName-$Environment" -ForegroundColor White
Write-Host "  To remove the Terraform workspace completely, run:" -ForegroundColor Cyan
Write-Host "   terraform workspace select default" -ForegroundColor White
Write-Host "   terraform workspace delete $Environment" -ForegroundColor White
```

### Step 3: Using the Destroy Scripts

**Mac/Linux:**
```bash
./scripts/destroy.sh dev
./scripts/destroy.sh test
./scripts/destroy.sh prod
```

**Windows (PowerShell):**
```powershell
.\scripts\destroy.ps1 -Environment dev
.\scripts\destroy.ps1 -Environment test
.\scripts\destroy.ps1 -Environment prod
```

### What Gets Destroyed

The destroy scripts will delete all resources Terraform created:
- Cloud Run service
- Cloud Storage bucket (force-destroyed, even with objects still in it)
- Artifact Registry repository
- Service account and its IAM bindings

**Not** deleted automatically: the Firebase Hosting site (run `firebase hosting:sites:delete` separately, as printed at the end of the script) and any Cloud Build history/logs, which cost nothing to leave in place.

### Important Notes

- **Cloud Run and Artifact Registry** delete almost immediately — no multi-minute "disable, then delete" dance like CloudFront
- **Workspaces**: the scripts destroy resources but keep the Terraform workspace. To fully remove one:
  ```bash
  terraform workspace select default
  terraform workspace delete dev  # or test, prod
  ```
- **Cost Savings**: always destroy unused environments to avoid charges

## Part 8: OPTIONAL - Add a Custom Domain

If you want a professional domain for your production twin, Firebase Hosting makes this considerably simpler than the AWS Route 53 + ACM + CloudFront dance — it's managed almost entirely through the console/CLI, with automatic SSL provisioning.

### Step 1: Register or Point a Domain

You can register a new domain through any registrar (GCP offers **Cloud Domains** if you'd like to buy one at `console.cloud.google.com/net-services/domains`), or use a domain you already own elsewhere.

### Step 2: Connect the Domain in Firebase Hosting

```bash
firebase hosting:sites:list          # confirm your prod site ID
firebase target:apply hosting prod twin-prod
cd frontend
firebase hosting:channel:deploy prod --only hosting:prod   # ensure prod has a live deploy first
```

Then, in the [Firebase console](https://console.firebase.google.com) → **Hosting** → select the `twin-prod` site → **Add custom domain**:

1. Enter your domain (e.g., `yourdomain.com`)
2. Firebase will show you one or two DNS records (usually `A` records, or a `TXT` record for verification) to add at your domain registrar or DNS provider
3. Add those records
4. Firebase automatically verifies ownership and provisions a managed SSL certificate — this typically takes anywhere from a few minutes to 24 hours

### Step 3: Update CORS on Cloud Run

Once the domain is live, update the backend's `CORS_ORIGINS` to include it:

```bash
gcloud run services update twin-prod-api \
  --region us-central1 \
  --set-env-vars CORS_ORIGINS=https://yourdomain.com,https://www.yourdomain.com
```

Or update `prod.tfvars` (see below) and redeploy through Terraform so it stays in version control.

### Step 4: Create Production Configuration

Create `terraform/prod.tfvars`:

```hcl
project_id               = "your-gcp-project-id"
project_name             = "twin"
environment              = "prod"
region                   = "us-central1"
gemini_model_id          = "gemini-2.5-flash"  # Use better model for production
cloud_run_timeout        = 60
cloud_run_min_instances  = 0
cloud_run_max_instances  = 10
cors_origins             = "https://yourdomain.com,https://www.yourdomain.com"
```

### Step 5: Deploy Production

**Mac/Linux:**
```bash
./scripts/deploy.sh prod
```

**Windows (PowerShell):**
```powershell
.\scripts\deploy.ps1 -Environment prod
```

### Step 6: Test Your Custom Domain

Once DNS has propagated and Firebase has provisioned the certificate:
1. Visit `https://yourdomain.com`
2. Visit `https://www.yourdomain.com` (if configured)
3. Both should show your Digital Twin!

## Understanding Terraform Workspaces

### How Workspaces Isolate Environments

Each workspace maintains its own state file:
```
terraform.tfstate.d/
├── dev/
│   └── terraform.tfstate
├── test/
│   └── terraform.tfstate
└── prod/
    └── terraform.tfstate
```

### Managing Workspaces

**List workspaces:**
```bash
terraform workspace list
```

**Switch workspace:**
```bash
terraform workspace select dev
```

**Show current workspace:**
```bash
terraform workspace show
```

### Resource Naming

Resources are named with an environment prefix:
- Dev: `twin-dev-api`, `twin-dev-memory-*`
- Test: `twin-test-api`, `twin-test-memory-*`
- Prod: `twin-prod-api`, `twin-prod-memory-*`

## Cost Optimization

### Environment-Specific Settings

Our configuration uses different settings per environment:

**Development:**
- Gemini Flash-Lite model (cheapest)
- Lower max instance count
- No custom domain

**Test:**
- Gemini Flash-Lite model
- Standard scaling
- No custom domain

**Production:**
- Gemini Flash model (better quality)
- Higher max instance count
- Custom domain with managed SSL

### Cost-Saving Tips

1. **Destroy unused environments** - Don't leave test running
2. **Use appropriate models** - Flash-Lite for dev/test
3. **Keep `cloud_run_min_instances = 0`** for non-prod - true scale-to-zero, no idle cost
4. **Monitor with labels** - All resources labeled with environment for cost breakdown in Billing reports

## Troubleshooting

### Terraform State Issues

If Terraform gets confused about resources:

```bash
# Refresh state from GCP
terraform refresh

# If resource exists in GCP but not state
terraform import google_cloud_run_v2_service.api projects/YOUR_PROJECT_ID/locations/us-central1/services/twin-dev-api
```

### Deployment Script Failures

**"Permission denied" during `gcloud builds submit`**
- Make sure the Cloud Build API is enabled and your user/service account has `roles/cloudbuild.builds.editor`

**"Bucket already exists"**
- Bucket names must be globally unique
- Change `project_name` in `terraform.tfvars`

**"Site already has a live channel"**
- If `firebase deploy` complains about an existing site, confirm you ran `firebase target:apply hosting <env> <site-id>` for the correct site before deploying

### Frontend Not Updating

Firebase Hosting invalidates its CDN cache automatically on every `firebase deploy`, so — unlike CloudFront — there's no manual invalidation step. If you still see stale content:

```bash
# Force a hard refresh, or verify the deploy actually completed:
firebase hosting:channel:list --site twin-dev
```

## Best Practices

### 1. Version Control

Always commit your Terraform files:
```bash
git add terraform/*.tf terraform/*.tfvars
git commit -m "Add Terraform infrastructure"
```

Never commit:
- `terraform.tfstate` files
- `.terraform/` directory
- GCP service account key files (we don't use any in this setup — Cloud Run and Cloud Build both use attached identities)

### 2. Plan Before Apply

Review changes before applying:
```bash
terraform plan
```

### 3. Use Variables

Don't hardcode values - use variables:
```hcl
# Good
name = "${local.name_prefix}-memory"

# Bad
name = "twin-dev-memory"
```

### 4. Label Everything

Our configuration labels all resources:
```hcl
labels = {
  project     = var.project_name
  environment = var.environment
  managed_by  = "terraform"
}
```

## What You've Accomplished Today!

- ✅ Learned Infrastructure as Code with Terraform
- ✅ Automated the entire GCP deployment
- ✅ Created multiple isolated environments
- ✅ Implemented one-command deployment
- ✅ Set up professional deployment scripts
- ✅ Optional: Configured a custom domain with managed SSL via Firebase Hosting

## Architecture Summary

Your Terraform manages:

```
Terraform Configuration
    ├── Cloud Storage Bucket (Memory)
    ├── Service Account with IAM bindings
    ├── Artifact Registry Repository
    ├── Cloud Run Service (built via Cloud Build)
    └── Public IAM invoker binding

Managed separately via Firebase CLI:
    ├── twin-dev    (Development frontend)
    ├── twin-test   (Testing frontend)
    └── twin-prod   (Production frontend, optional custom domain)

Managed via Terraform Workspaces:
    ├── dev/   (Development environment)
    ├── test/  (Testing environment)
    └── prod/  (Production environment)
```

## Next Steps

Tomorrow (Day 5), we'll add CI/CD with GitHub Actions:
- Automated testing on pull requests
- Deployment pipelines for each environment
- Infrastructure change reviews
- Automated rollbacks
- Complete infrastructure teardown

Your Digital Twin now has professional Infrastructure as Code that any team can deploy and manage!

## Resources

- [Terraform Documentation](https://www.terraform.io/docs)
- [Terraform Google Provider](https://registry.terraform.io/providers/hashicorp/google/latest)
- [Terraform Best Practices](https://www.terraform-best-practices.com/)
- [GCP IAM Best Practices](https://cloud.google.com/iam/docs/using-iam-securely)

Congratulations on automating your infrastructure deployment! 🚀
