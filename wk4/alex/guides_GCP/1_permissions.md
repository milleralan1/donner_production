# Building Alex: Part 1 - Google Cloud Project and IAM

In this guide, prepare a Google Cloud project for Alex. The AWS guide's IAM users and groups do not map directly to Google Cloud: use Cloud Identity/Google accounts for people and dedicated service accounts for workloads.

## What you'll set up

- A dedicated Google Cloud project with billing attached
- The `gcloud` CLI and Application Default Credentials (ADC)
- Required API enablement
- A project-specific deployment identity and budget alerts

## Prerequisites

- A Google account with permission to create or select a Cloud project and attach billing
- Google Cloud CLI (`gcloud`) installed
- Terraform 1.5+ for later guides
- Docker and `uv` for application work

Use an organization or billing account only as required by your administrator. Do not use an owner-level account for routine deployments.

## Step 1: Create or select a project

In the Google Cloud Console, create a dedicated project such as `alex-gcp-dev`, attach a billing account, and note its **project ID** (not just its display name). Set a region supported by the services and models you choose; keep resources in that region where practical.

```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
gcloud config set run/region YOUR_REGION
gcloud config list
gcloud projects describe YOUR_PROJECT_ID
```

Create a budget and email notifications in **Billing → Budgets & alerts**. Budgets notify you; they do not automatically cap spending. Review billing regularly.

## Step 2: Enable APIs as you progress

Enable only the APIs needed for the next deployment. The following set covers the planned guides; some APIs may require project-level permissions or additional setup:

```bash
gcloud services enable \
  aiplatform.googleapis.com \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  storage.googleapis.com \
  sqladmin.googleapis.com \
  secretmanager.googleapis.com \
  pubsub.googleapis.com \
  cloudscheduler.googleapis.com \
  logging.googleapis.com \
  monitoring.googleapis.com \
  apigateway.googleapis.com \
  servicecontrol.googleapis.com \
  servicemanagement.googleapis.com
```

Verify enabled services:

```bash
gcloud services list --enabled
```

Enable `compute.googleapis.com` if a selected service or Terraform resource requires it. Do not enable APIs from an unverified command or grant broad project roles merely to bypass an error.

## Step 3: Choose deployment credentials

For local development, authenticate ADC:

```bash
gcloud auth application-default login
gcloud auth application-default set-quota-project YOUR_PROJECT_ID
```

For deployment automation, prefer workload identity federation. If a service account key is unavoidable for a learning environment, protect it outside the repository and rotate/delete it when no longer needed. Never commit a key file.

Create separate service accounts for Terraform deployment and runtime workloads. Grant runtime identities only the roles they need. Typical runtime permissions may include:

- Vertex AI model invocation: `roles/aiplatform.user`
- Read an individual secret: `roles/secretmanager.secretAccessor` on that secret
- Read/write objects in a specific bucket: an appropriate Cloud Storage object role scoped to that bucket
- Publish or consume messages: Pub/Sub publisher/subscriber roles scoped to the relevant topic/subscription
- Connect to Cloud SQL: `roles/cloudsql.client`

Resource creation roles should be assigned deliberately to the deployment identity, not copied onto every runtime service account. Follow organizational IAM policy and least privilege.

## Step 4: Record project configuration

Keep non-secret identifiers in a local `.env` file (already gitignored where configured) or your deployment configuration:

```dotenv
GOOGLE_CLOUD_PROJECT=YOUR_PROJECT_ID
GOOGLE_CLOUD_REGION=YOUR_REGION
```

Do not add AWS values such as `AWS_ACCOUNT_ID`, `DEFAULT_AWS_REGION`, or ARNs to the GCP configuration. Confirm `.env` is ignored before storing any local settings; secrets belong in Secret Manager.

## Step 5: Verify access

```bash
gcloud auth list
gcloud config get-value project
gcloud projects get-iam-policy YOUR_PROJECT_ID
```

An IAM permission error is not evidence that a broader role should be granted. Identify the principal, denied permission, target resource, and intended operation, then grant the narrowest appropriate role.

## Infrastructure organization

Use a separate Terraform directory and state for each guide, mirroring the educational isolation of the AWS setup. The current `terraform/2_sagemaker`, `3_ingestion`, and other directories are AWS-only and must not be reused as GCP configurations. Create separate GCP directories/modules, review `terraform plan`, and protect each state file because it can contain sensitive values.

## Next

Continue to [2_embeddings.md](2_embeddings.md) to select and test an embedding model in Vertex AI.
