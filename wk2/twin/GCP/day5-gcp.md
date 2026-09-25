# Day 5: CI/CD with GitHub Actions

## From Local Development to Professional DevOps

Welcome to the final day of Week 2! Today we're implementing the complete DevOps lifecycle - from version control to continuous deployment to infrastructure teardown. You'll set up GitHub Actions to automatically deploy your Digital Twin whenever you push code, manage multiple environments through a web interface, and ensure everything can be cleanly removed when you're done. This is how professional teams manage production infrastructure!

## What You'll Learn Today

- **Git and GitHub** - Version control for infrastructure and code
- **Remote state management** - Terraform state in Cloud Storage with native locking
- **GitHub Actions** - CI/CD pipelines for automated deployment
- **GitHub Secrets** - Secure credential management
- **Workload Identity Federation** - Modern GCP authentication without service account keys
- **Multi-environment workflows** - Automated and manual deployments
- **Infrastructure cleanup** - Complete teardown strategies

## Part 1: Clean Up Existing Infrastructure

Before setting up CI/CD, let's remove all existing environments to start fresh.

### Step 1: Destroy All Environments

We'll use the destroy scripts created on Day 4 to clean up dev, test, and prod environments.

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

Each destruction typically takes 1-3 minutes — much faster than waiting on CloudFront distribution teardown.

### Step 2: Clean Up Terraform Workspaces

```bash
cd terraform
terraform workspace select default
terraform workspace delete dev
terraform workspace delete test
terraform workspace delete prod
cd ..
```

### Step 3: Verify Clean State

```bash
gcloud run services list
gcloud storage buckets list
gcloud artifacts repositories list --location us-central1
```

None of these should show any `twin-` prefixed resources.

✅ **Checkpoint**: Your GCP project is now clean, ready for CI/CD deployment!

## Part 2: Initialize Git Repository

### Step 1: Create .gitignore

Ensure your `.gitignore` in the project root (`twin/.gitignore`) is complete:

```gitignore
# Terraform
*.tfstate
*.tfstate.*
.terraform/
.terraform.lock.hcl
terraform.tfstate.d/
*.tfvars.secret

# Memory storage (contains conversation history)
memory/

# Environment files
.env
.env.*
!.env.example

# Node
node_modules/
out/
.next/
*.log

# Python
__pycache__/
*.pyc
.venv/
venv/

# IDE
.vscode/
.idea/
*.swp
.DS_Store
Thumbs.db

# GCP
*.json.key
gcloud-key.json
```

### Step 2: Create Example Environment File

Create `.env.example` to help others understand required environment variables:

```bash
# GCP Configuration
GCP_PROJECT_ID=your-gcp-project-id
GCP_REGION=us-central1

# Project Configuration
PROJECT_NAME=twin
```

### Step 3: Initialize Git Repository

First, clean up any git repositories that might have been created by the tooling:

**Mac/Linux:**
```bash
cd twin

rm -rf frontend/.git backend/.git 2>/dev/null

git init -b main
# If you get an error that -b is not supported (older Git versions), use:
# git init
# git checkout -b main

git config user.name "Your Name"
git config user.email "your.email@example.com"
```

**Windows (PowerShell):**
```powershell
cd twin

Remove-Item -Path frontend/.git -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path backend/.git -Recurse -Force -ErrorAction SilentlyContinue

git init -b main
# If you get an error that -b is not supported (older Git versions), use:
# git init
# git checkout -b main

git config user.name "Your Name"
git config user.email "your.email@example.com"
```

After configuring git, continue with adding and committing files:

```bash
git add .
git commit -m "Initial commit: Digital Twin infrastructure and application"
```

### Step 4: Create GitHub Repository

1. Go to [github.com](https://github.com) and sign in
2. Click the **+** icon in the top right → **New repository**
3. Configure your repository:
   - Repository name: `digital-twin` (or your preferred name)
   - Description: "AI Digital Twin deployed on GCP with Terraform"
   - Public or Private: Your choice (private recommended if using real personal data)
   - DO NOT initialize with README, .gitignore, or license
4. Click **Create repository**

### Step 5: Push to GitHub

```bash
git remote add origin https://github.com/YOUR_USERNAME/digital-twin.git
git push -u origin main
```

If prompted for authentication:
- Username: Your GitHub username
- Password: Use a Personal Access Token (not your password)
  - Go to GitHub → Settings → Developer settings → Personal access tokens
  - Generate a token with `repo` scope

✅ **Checkpoint**: Your code is now on GitHub! Refresh your GitHub repository page to see all files.

## Part 3: Set Up a Cloud Storage Backend for Terraform State

On AWS, storing Terraform state remotely required an S3 bucket **and** a DynamoDB table for locking. On GCP, the `gcs` backend has locking built in via object generation preconditions — so you only need one bucket, no separate lock table.

### Step 1: Create State Management Resources

Create `terraform/backend-setup.tf`:

```hcl
# This file creates the Cloud Storage bucket for Terraform state
# Run this once per GCP project, then remove the file

resource "google_storage_bucket" "terraform_state" {
  name                        = "twin-terraform-state-${data.google_project.current.number}"
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
```

### Step 2: Create the Backend Resources

```bash
cd terraform

# IMPORTANT: Make sure you're in the default workspace
terraform workspace select default

terraform init

# Apply just the state bucket
terraform apply -target=google_storage_bucket.terraform_state

# Verify
terraform output state_bucket_name
```

### Step 3: Remove the Setup File

```bash
rm backend-setup.tf          # Mac/Linux
Remove-Item backend-setup.tf # Windows PowerShell
```

### Step 4: Configure the Terraform Backend

Create `terraform/backend.tf`:

```hcl
terraform {
  backend "gcs" {
    # bucket and prefix are supplied by deployment scripts via -backend-config
  }
}
```

### Step 5: Update Scripts for the GCS Backend

Update `scripts/deploy.sh` — find the `terraform init -input=false` line and replace it:

```bash
# Old line:
terraform init -input=false

# New lines:
PROJECT_NUMBER=$(gcloud projects describe "$(gcloud config get-value project)" --format="value(projectNumber)")
terraform init -input=false \
  -backend-config="bucket=twin-terraform-state-${PROJECT_NUMBER}" \
  -backend-config="prefix=terraform/state/${ENVIRONMENT}"
```

Update `scripts/deploy.ps1` similarly:

```powershell
# Old line:
terraform init -input=false

# New lines:
$projectNumber = gcloud projects describe (gcloud config get-value project) --format="value(projectNumber)"
terraform init -input=false `
  -backend-config="bucket=twin-terraform-state-$projectNumber" `
  -backend-config="prefix=terraform/state/$Environment"
```

Update `scripts/destroy.sh` the same way — add the same `PROJECT_NUMBER` lookup and `terraform init -input=false -backend-config=...` block right after `cd "$(dirname "$0")/../terraform"` and before the workspace check. Do the equivalent in `scripts/destroy.ps1`.

Because our Cloud Storage buckets use `force_destroy = true`, the destroy scripts from Day 4 don't need any "empty the bucket first" logic — that entire step from the AWS version simply isn't needed here.

## Part 4: Configure GitHub Repository Secrets

### Step 1: Create a Workload Identity Pool for GitHub Actions

As of 2025, both AWS and GCP steer users toward federated, keyless authentication for CI/CD. On GCP, this is **Workload Identity Federation (WIF)** — GitHub Actions presents its own OIDC token, GCP verifies it against GitHub's issuer, and grants a short-lived token to impersonate a service account. No JSON key files, ever.

Create `terraform/github-wif.tf`:

```hcl
# This creates a Workload Identity Pool that GitHub Actions can use
# to authenticate to GCP without a service account key.
# Run this once, then you can remove the file.

variable "github_repository" {
  description = "GitHub repository in format 'owner/repo'"
  type        = string
}

resource "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = "github-actions-pool"
  display_name              = "GitHub Actions Pool"
  description               = "Used by GitHub Actions to deploy the Digital Twin"
}

resource "google_iam_workload_identity_pool_provider" "github" {
  workload_identity_pool_id         = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-provider"
  display_name                      = "GitHub Provider"

  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
    "attribute.ref"        = "assertion.ref"
  }

  # Restrict to only this repository
  attribute_condition = "assertion.repository == \"${var.github_repository}\""

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

# Service account that GitHub Actions will impersonate
resource "google_service_account" "github_actions" {
  account_id   = "github-actions-twin-deploy"
  display_name = "GitHub Actions Deploy"
}

# Grant the necessary project-level roles
resource "google_project_iam_member" "github_run_admin" {
  project = var.project_id
  role    = "roles/run.admin"
  member  = "serviceAccount:${google_service_account.github_actions.email}"
}

resource "google_project_iam_member" "github_storage_admin" {
  project = var.project_id
  role    = "roles/storage.admin"
  member  = "serviceAccount:${google_service_account.github_actions.email}"
}

resource "google_project_iam_member" "github_artifact_admin" {
  project = var.project_id
  role    = "roles/artifactregistry.admin"
  member  = "serviceAccount:${google_service_account.github_actions.email}"
}

resource "google_project_iam_member" "github_cloudbuild_editor" {
  project = var.project_id
  role    = "roles/cloudbuild.builds.editor"
  member  = "serviceAccount:${google_service_account.github_actions.email}"
}

resource "google_project_iam_member" "github_iam_admin" {
  project = var.project_id
  role    = "roles/resourcemanager.projectIamAdmin"
  member  = "serviceAccount:${google_service_account.github_actions.email}"
}

resource "google_project_iam_member" "github_sa_user" {
  project = var.project_id
  role    = "roles/iam.serviceAccountUser"
  member  = "serviceAccount:${google_service_account.github_actions.email}"
}

resource "google_project_iam_member" "github_sa_admin" {
  project = var.project_id
  role    = "roles/iam.serviceAccountAdmin"
  member  = "serviceAccount:${google_service_account.github_actions.email}"
}

# Allow the GitHub Actions OIDC identity to impersonate this service account
resource "google_service_account_iam_member" "github_wif_binding" {
  service_account_id = google_service_account.github_actions.name
  role                = "roles/iam.workloadIdentityUser"
  member              = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/${var.github_repository}"
}

output "workload_identity_provider" {
  value = google_iam_workload_identity_pool_provider.github.name
}

output "github_actions_service_account" {
  value = google_service_account.github_actions.email
}
```

### Step 2: Apply the Workload Identity Resources

**⚠️ IMPORTANT**: Replace `YOUR_GITHUB_USERNAME` with your actual GitHub username. For example, if your GitHub username is `johndoe`, use: `johndoe/digital-twin`.

```bash
cd terraform
terraform workspace select default

terraform apply \
  -target=google_iam_workload_identity_pool.github \
  -target=google_iam_workload_identity_pool_provider.github \
  -target=google_service_account.github_actions \
  -target=google_project_iam_member.github_run_admin \
  -target=google_project_iam_member.github_storage_admin \
  -target=google_project_iam_member.github_artifact_admin \
  -target=google_project_iam_member.github_cloudbuild_editor \
  -target=google_project_iam_member.github_iam_admin \
  -target=google_project_iam_member.github_sa_user \
  -target=google_project_iam_member.github_sa_admin \
  -target=google_service_account_iam_member.github_wif_binding \
  -var="github_repository=YOUR_GITHUB_USERNAME/digital-twin"
```

### Step 3: Save the Outputs and Clean Up

```bash
terraform output workload_identity_provider
terraform output github_actions_service_account

rm github-wif.tf          # Mac/Linux
Remove-Item github-wif.tf # Windows PowerShell
```

Save both output values — you'll need them for GitHub secrets next.

### Step 4: Add Secrets to GitHub

1. Go to your GitHub repository
2. Click **Settings** tab
3. In the left sidebar, click **Secrets and variables** → **Actions**
4. Click **New repository secret** for each of these:

**Secret 1: GCP_PROJECT_ID**
- Name: `GCP_PROJECT_ID`
- Value: Your GCP project ID

**Secret 2: GCP_WIF_PROVIDER**
- Name: `GCP_WIF_PROVIDER`
- Value: The `workload_identity_provider` output from Step 3 (looks like `projects/123456789/locations/global/workloadIdentityPools/github-actions-pool/providers/github-provider`)

**Secret 3: GCP_SERVICE_ACCOUNT**
- Name: `GCP_SERVICE_ACCOUNT`
- Value: The `github_actions_service_account` output from Step 3 (looks like `github-actions-twin-deploy@your-project.iam.gserviceaccount.com`)

**Secret 4: GCP_REGION**
- Name: `GCP_REGION`
- Value: `us-central1` (or your preferred region)

**Secret 5: FIREBASE_TOKEN** (for deploying the frontend from CI)
- Generate this locally first: `firebase login:ci`
- Name: `FIREBASE_TOKEN`
- Value: the token printed by that command

### Step 5: Verify Secrets

After adding all secrets, you should see 5 repository secrets:
- GCP_PROJECT_ID
- GCP_WIF_PROVIDER
- GCP_SERVICE_ACCOUNT
- GCP_REGION
- FIREBASE_TOKEN

✅ **Checkpoint**: GitHub can now securely authenticate with your GCP project — no static keys involved!

## Part 5: Create GitHub Actions Workflows

### Step 1: Create Workflow Directory

Create `.github/workflows/` in your project (a `.github` folder containing a `workflows` folder).

### Step 2: Create Deployment Workflow

Create `.github/workflows/deploy.yml`:

```yaml
name: Deploy Digital Twin

on:
  push:
    branches: [main]
  workflow_dispatch:
    inputs:
      environment:
        description: 'Environment to deploy'
        required: true
        default: 'dev'
        type: choice
        options:
          - dev
          - test
          - prod

permissions:
  id-token: write
  contents: read

jobs:
  deploy:
    name: Deploy to ${{ github.event.inputs.environment || 'dev' }}
    runs-on: ubuntu-latest
    environment: ${{ github.event.inputs.environment || 'dev' }}

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Authenticate to Google Cloud
        uses: google-github-actions/auth@v2
        with:
          workload_identity_provider: ${{ secrets.GCP_WIF_PROVIDER }}
          service_account: ${{ secrets.GCP_SERVICE_ACCOUNT }}

      - name: Set up Cloud SDK
        uses: google-github-actions/setup-gcloud@v2
        with:
          project_id: ${{ secrets.GCP_PROJECT_ID }}

      - name: Setup Terraform
        uses: hashicorp/setup-terraform@v3
        with:
          terraform_wrapper: false  # Important: disable wrapper to get raw outputs

      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'
          cache-dependency-path: frontend/package-lock.json

      - name: Install Firebase CLI
        run: npm install -g firebase-tools

      - name: Run Deployment Script
        run: |
          chmod +x scripts/deploy.sh
          ./scripts/deploy.sh ${{ github.event.inputs.environment || 'dev' }}
        env:
          GCP_PROJECT_ID: ${{ secrets.GCP_PROJECT_ID }}
          GCP_REGION: ${{ secrets.GCP_REGION }}
          FIREBASE_TOKEN: ${{ secrets.FIREBASE_TOKEN }}

      - name: Get Deployment URL
        id: deploy_outputs
        working-directory: ./terraform
        run: |
          terraform workspace select ${{ github.event.inputs.environment || 'dev' }}
          echo "cloud_run_url=$(terraform output -raw cloud_run_url)" >> $GITHUB_OUTPUT

      - name: Deployment Summary
        run: |
          echo "✅ Deployment Complete!"
          echo "📡 Cloud Run URL: ${{ steps.deploy_outputs.outputs.cloud_run_url }}"
          echo "🌐 Firebase Hosting: run 'firebase hosting:sites:list' or check the Firebase console"
```

Note there's no separate "invalidate the CDN" step, unlike the CloudFront workflow — Firebase Hosting's `firebase deploy` (run inside `scripts/deploy.sh`) already invalidates its own cache on every deploy.

### Step 3: Create Destroy Workflow

Create `.github/workflows/destroy.yml`:

```yaml
name: Destroy Environment

on:
  workflow_dispatch:
    inputs:
      environment:
        description: 'Environment to destroy'
        required: true
        type: choice
        options:
          - dev
          - test
          - prod
      confirm:
        description: 'Type the environment name to confirm destruction'
        required: true

permissions:
  id-token: write
  contents: read

jobs:
  destroy:
    name: Destroy ${{ github.event.inputs.environment }}
    runs-on: ubuntu-latest
    environment: ${{ github.event.inputs.environment }}

    steps:
      - name: Verify confirmation
        run: |
          if [ "${{ github.event.inputs.confirm }}" != "${{ github.event.inputs.environment }}" ]; then
            echo "❌ Confirmation does not match environment name!"
            exit 1
          fi
          echo "✅ Destruction confirmed for ${{ github.event.inputs.environment }}"

      - name: Checkout code
        uses: actions/checkout@v4

      - name: Authenticate to Google Cloud
        uses: google-github-actions/auth@v2
        with:
          workload_identity_provider: ${{ secrets.GCP_WIF_PROVIDER }}
          service_account: ${{ secrets.GCP_SERVICE_ACCOUNT }}

      - name: Set up Cloud SDK
        uses: google-github-actions/setup-gcloud@v2
        with:
          project_id: ${{ secrets.GCP_PROJECT_ID }}

      - name: Setup Terraform
        uses: hashicorp/setup-terraform@v3
        with:
          terraform_wrapper: false

      - name: Run Destroy Script
        run: |
          chmod +x scripts/destroy.sh
          ./scripts/destroy.sh ${{ github.event.inputs.environment }}
        env:
          GCP_PROJECT_ID: ${{ secrets.GCP_PROJECT_ID }}
          GCP_REGION: ${{ secrets.GCP_REGION }}

      - name: Destruction Complete
        run: echo "✅ Environment ${{ github.event.inputs.environment }} has been destroyed!"
```

### Step 4: Commit and Push All Changes

```bash
git add .
git status
git commit -m "Add CI/CD with GitHub Actions, GCS backend, and updated scripts"
git push
```

## Part 6: Test Deployments

### Step 1: Automatic Dev Deployment

Since we pushed to the main branch, GitHub Actions should automatically trigger a deployment to dev:

1. Go to your GitHub repository → **Actions** tab
2. You should see "Deploy Digital Twin" workflow running
3. Click on it to watch the progress
4. Wait for completion (typically 3-6 minutes — Cloud Build is fast)
5. Expand the **"Deployment Summary"** step to see your Cloud Run URL
6. Run `firebase hosting:sites:list` (or check the Firebase console) for your Hosting URL, and open it in a browser

### Step 2: Manual Test Deployment

1. In GitHub, go to **Actions** → **Deploy Digital Twin** → **Run workflow**
2. Select branch `main`, environment `test`
3. Click **Run workflow** and watch the progress

### Step 3: Manual Production Deployment

If you have a custom domain configured (Day 4, Part 8):

1. **Actions** → **Deploy Digital Twin** → **Run workflow**
2. Select branch `main`, environment `prod`
3. Click **Run workflow**

### Step 4: Verify Deployments

After each deployment completes, check the workflow summary for the Cloud Run URL, visit the corresponding Firebase Hosting URL, and have a conversation to verify it's working.

✅ **Checkpoint**: You now have CI/CD deploying to multiple environments!

## Part 7: Fix UI Focus Issue and Add Avatar

This part is entirely frontend code and has no cloud-provider-specific content — follow it exactly as written in the original guide: add an `inputRef`, refocus the input after each response in the `finally` block of `sendMessage`, and optionally drop a square `avatar.png` into `frontend/public/`. Commit and push as usual:

```bash
git add frontend/components/twin.tsx
git add frontend/public/avatar.png  # Only if you added an avatar
git commit -m "Fix input focus issue and add avatar support"
git push
```

This push will automatically trigger a deployment to dev, just like any other change.

## Part 8: Explore the GCP Console and Cloud Logging

Now let's explore what's happening behind the scenes in GCP.

### Step 1: Explore Cloud Run Services

1. Navigate to **Cloud Run** in the console
2. You should see three services:
   - `twin-dev-api`
   - `twin-test-api`
   - `twin-prod-api` (if deployed)
3. Click on `twin-dev-api` → **Metrics** tab to view:
   - Request count
   - Request latency
   - Container instance count
   - Error rate

### Step 2: View Cloud Run Logs

1. From the Cloud Run service page, click **Logs**
2. You can see:
   - Each API request
   - Vertex AI model calls
   - Response times
   - Any errors

### Step 3: Check Vertex AI Usage

1. Navigate to **Monitoring → Metrics Explorer**
2. Search for the **Vertex AI Publisher Model** resource type
3. View metrics for your Gemini model: invocation count, latency, token counts

### Step 4: View Cloud Storage Memory Bucket

1. Navigate to **Cloud Storage → Buckets**
2. Click on `twin-dev-memory-*`
3. You'll see a JSON object for each conversation session
4. Click on an object to view the conversation history

### Step 5: Cloud Build History

1. Navigate to **Cloud Build → History**
2. See every container build triggered by Terraform's `gcloud builds submit` calls, with full logs for each

### Step 6: Firebase Hosting Usage

1. Open the [Firebase console](https://console.firebase.google.com) → your project → **Hosting**
2. View release history, bandwidth usage, and connected domains per site

## Part 9: Environment Management via GitHub

### Step 1: Test Environment Destruction

1. Go to your GitHub repository → **Actions** → **Destroy Environment** → **Run workflow**
2. Select branch `main`, environment `test`, and type `test` in the confirmation field
3. Click **Run workflow** and watch the destruction progress (typically 1-3 minutes)

### Step 2: Verify Destruction

```bash
gcloud run services list --filter="metadata.name:twin-test"
gcloud storage buckets list --filter="name:twin-test"
```

Both should return nothing.

### Step 3: Redeploy Test

1. **Actions** → **Deploy Digital Twin** → **Run workflow** with environment `test`
2. Wait for completion, then verify the test environment is back online

## Part 10: Final Cleanup and Cost Review

### Step 1: Destroy All Environments

Use GitHub Actions to destroy `dev`, `test`, and `prod` (if created) the same way as Part 9, Step 1.

### Step 2: Verify Complete Cleanup

```bash
gcloud run services list
gcloud storage buckets list
gcloud artifacts repositories list --location us-central1
```

Only the `twin-terraform-state-*` bucket should remain — everything else Terraform created for `dev`/`test`/`prod` should be gone. The `github-actions-twin-deploy` service account and Workload Identity Pool should still exist (they're not tied to any one environment).

You can also get a full inventory of tagged resources with **Cloud Asset Inventory**:

```bash
gcloud asset search-all-resources \
  --scope="projects/YOUR_PROJECT_ID" \
  --query="labels.project=twin"
```

Or, to see literally everything in the project regardless of labels:

```bash
gcloud asset search-all-resources --scope="projects/YOUR_PROJECT_ID"
```

### Step 3: Review Costs

1. Go to **Billing → Reports**
2. Set the date range to the last 7 days
3. Filter/group by service to see costs:
   - Cloud Run: usually under $1
   - Cloud Storage: minimal (cents)
   - Vertex AI: depends on usage, typically under $5
   - Cloud Build: minimal (free tier covers most course usage)
   - Firebase Hosting: free tier covers this project comfortably

### Step 4: Optional - Clean Up CI/CD Resources

The remaining resources have minimal-to-zero ongoing cost:
- **Workload Identity Pool & `github-actions-twin-deploy` service account**: FREE — no cost for IAM
- **Terraform state bucket** (`twin-terraform-state-*`): a few cents/month for storing state files

**Total monthly cost if left running: well under $0.10**

If you want to completely remove everything (only do this if you're completely done with the course):

```bash
cd twin/terraform

# 1. Remove the IAM bindings and service account for GitHub Actions
gcloud iam service-accounts delete github-actions-twin-deploy@YOUR_PROJECT_ID.iam.gserviceaccount.com

# 2. Delete the Workload Identity Pool (this also removes its provider)
gcloud iam workload-identity-pools delete github-actions-pool --location=global

# 3. Empty and delete the state bucket
PROJECT_NUMBER=$(gcloud projects describe YOUR_PROJECT_ID --format="value(projectNumber)")
gcloud storage rm -r "gs://twin-terraform-state-${PROJECT_NUMBER}"
```

**Recommendation**: leave these resources in place. They cost almost nothing and let you redeploy the project later if needed.

## Congratulations! 🎉

You've successfully completed Week 2 and built a production-grade AI deployment system!

### What You've Accomplished This Week

**Day 1**: Built a local Digital Twin with memory
**Day 2**: Deployed to GCP with Cloud Run, Cloud Storage, Firebase Hosting
**Day 3**: Integrated Vertex AI (Gemini) for AI responses
**Day 4**: Automated with Terraform and multiple environments
**Day 5**: Implemented CI/CD with GitHub Actions

### Your Final Architecture

```
GitHub Repository
    ↓ (Push to main)
GitHub Actions (CI/CD, authenticated via Workload Identity Federation)
    ↓ (Automated deployment)
GCP Infrastructure
    ├── Dev Environment
    ├── Test Environment
    └── Prod Environment

Each Environment:
    ├── Firebase Hosting (Frontend, global CDN + HTTPS)
    ├── Cloud Run (Backend)
    ├── Vertex AI / Gemini (AI)
    └── Cloud Storage (Memory)

All Managed by:
    ├── Terraform (IaC)
    ├── GitHub Actions (CI/CD)
    └── Cloud Storage (State, with native locking)
```

### Key Skills You've Learned

1. **Modern DevOps Practices**
   - Infrastructure as Code
   - CI/CD pipelines
   - Multi-environment management
   - Automated testing and deployment

2. **GCP Services Mastery**
   - Serverless containers (Cloud Run)
   - Managed static hosting + CDN (Firebase Hosting)
   - Generative AI services (Vertex AI)
   - State management (Cloud Storage with native locking)

3. **Security Best Practices**
   - Workload Identity Federation (keyless CI/CD auth)
   - IAM roles and least-privilege service accounts
   - Secrets management
   - Least privilege access

4. **Professional Development Workflow**
   - Version control with Git
   - Pull request workflows
   - Automated deployments
   - Infrastructure testing

## Best Practices Going Forward

### Development Workflow

1. **Always use branches for features** (even though we didn't today)
   ```bash
   git checkout -b feature/new-feature
   git push -u origin feature/new-feature
   ```

2. **Test in dev/test before prod**
   - Deploy to dev automatically
   - Manually promote to test
   - Carefully deploy to prod

3. **Monitor costs regularly**
   - Check Cloud Monitoring metrics
   - Review the Billing dashboard weekly
   - Set up budget alerts and anomaly detection

### Security Reminders

1. **Never commit secrets**
   - Use GitHub Secrets
   - Use environment variables
   - Use Secret Manager for sensitive data if you outgrow env vars

2. **Rotate credentials regularly**
   - Review Workload Identity Pool conditions periodically
   - Refresh the `FIREBASE_TOKEN` if it's ever exposed
   - Review IAM audit logs

3. **Follow least privilege**
   - Only grant necessary IAM roles
   - Use separate service accounts for different purposes
   - Audit permissions regularly with `gcloud projects get-iam-policy`

## Troubleshooting Common Issues

### GitHub Actions Failures

**"Permission denied" / "unable to impersonate service account"**
- Check the `GCP_WIF_PROVIDER` and `GCP_SERVICE_ACCOUNT` secrets are correct
- Verify the GitHub repository name matches the `attribute_condition` on the WIF provider exactly
- Ensure the `google_service_account_iam_member` binding is in place

**"Terraform state lock"**
- Someone else might be deploying, or a previous run was interrupted
- Force unlock if needed: `terraform force-unlock LOCK_ID`

**"Bucket already exists"**
- Bucket names must be globally unique
- Change `project_name` in `terraform.tfvars`

### Deployment Issues

**Frontend not updating**
- Check the GitHub Actions run completed successfully
- Verify `firebase deploy` completed without errors in the logs

**API returning 403**
- Check CORS configuration on Cloud Run
- Verify the `google_cloud_run_v2_service_iam_member.public` binding is still in place

**Vertex AI not responding**
- Verify the `aiplatform.googleapis.com` API is enabled
- Check the runtime service account has `roles/aiplatform.user`
- Review Cloud Logging for the exact error

## Next Steps and Extensions

### Potential Enhancements

1. **Add Testing**
   - Unit tests for the FastAPI backend
   - Integration tests for the API
   - End-to-end tests with Playwright/Cypress

2. **Enhance Monitoring**
   - Custom Cloud Monitoring dashboards
   - Alerting policies for errors
   - Uptime checks

3. **Add Features**
   - User authentication (Firebase Auth pairs naturally here)
   - Multiple twin personalities
   - Conversation analytics
   - Voice interface

4. **Improve CI/CD**
   - Blue-green deployments (Cloud Run supports traffic splitting natively)
   - Canary releases
   - Automatic rollbacks

### Learning Resources

- [GitHub Actions Documentation](https://docs.github.com/actions)
- [Google Cloud Architecture Framework](https://cloud.google.com/architecture/framework)
- [Terraform Best Practices](https://www.terraform.io/docs/cloud/guides/recommended-practices)
- [GCP DevOps Resources](https://cloud.google.com/devops)

## Final Notes

### Keeping Costs Low

To minimize ongoing costs:
1. Destroy environments when not in use
2. Use Gemini Flash-Lite for development
3. Keep `cloud_run_min_instances = 0` outside of production
4. Monitor usage regularly
5. Use the GCP Free Tier effectively (Cloud Run, Cloud Build, and Firebase Hosting all have generous always-free tiers)

### Repository Maintenance

Keep your repository healthy:
1. Regular dependency updates
2. Security scanning with Dependabot
3. Clear documentation
4. Meaningful commit messages
5. Protected main branch

You've built something amazing - a fully automated, production-ready AI application with professional DevOps practices. This is how real companies deploy and manage their infrastructure!

Great job completing Week 2! 🚀
