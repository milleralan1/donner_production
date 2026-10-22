# Building Alex: Part 7 - Frontend and API on Google Cloud

Deploy the Next.js application and FastAPI API on Cloud Run while retaining Clerk for authentication. Clerk remains the identity provider; GCP IAM secures service-to-service calls and does not replace user JWT validation. The original AWS S3/CloudFront/Lambda deployment remains unchanged.

## Prerequisites

- Completed Guides 1-6
- Node.js 20+, npm, Python with `uv`, Docker, and Terraform
- Clerk publishable/secret keys and the Clerk JWKS URL
- GCP API and agent endpoints configured
- The `alex-api` service account is listed in `terraform_gcp/5_database`'s `runtime_service_accounts`
- Layer 6's `alex-analysis-jobs` Pub/Sub topic and topic-scoped publisher grant for `alex-api`

## Step 1: Configure Clerk and local development

Use the existing Clerk application or create one. Keep public and server-side credentials separate:

```dotenv
# frontend/.env.local
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_REPLACE_ME
CLERK_SECRET_KEY=sk_test_REPLACE_ME
NEXT_PUBLIC_CLERK_AFTER_SIGN_IN_URL=/dashboard
NEXT_PUBLIC_CLERK_AFTER_SIGN_UP_URL=/dashboard
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Place Clerk secret keys in local-only configuration or Secret Manager; never commit them. Configure the API with the correct Clerk issuer and JWKS URL. Continue to validate tokens server-side on every protected request and derive the user identity from the verified token, not request payloads.

Run the existing local app and confirm login, account CRUD, and test data work before cloud deployment. AI analysis requires the GCP backend services to be deployed.

The API uses the existing Clerk JWT verifier for signature/expiry validation and additionally checks `CLERK_ISSUER` when configured. Set it to the exact issuer from the Clerk instance. It never trusts a caller-supplied user ID.

## Step 2: Prepare the Clerk secret

Create a Secret Manager secret named `alex-clerk-secret-key` (or the name you choose in Terraform) and add the Clerk **secret key** version through Google Cloud Console → Secret Manager. Do not put the key in `terraform.tfvars`, Docker build arguments, or source control. The Cloud Run frontend service account receives access to this one secret. The publishable key is public and is passed to the frontend image build.

## Step 3: Configure the GCP Terraform stack

The GCP stack is separate from the AWS `terraform/7_frontend` directory:

```bash
cd terraform_gcp/7_frontend
cp terraform.tfvars.example terraform.tfvars
```

Set project, region, the existing API service account email, Cloud SQL connection name and secret ID, Layer 6 topic ID, Clerk JWKS URL and issuer, the Clerk publishable key, and the Secret Manager secret ID. `api_image_url` and `frontend_image_url` must be valid repository paths even before the images exist. `frontend_origin` should remain empty for the first deployment. Keep passwords and Clerk secret keys out of this file.

Initialize the independent stack and create its Artifact Registry repository:

```bash
terraform init
terraform validate
terraform apply -target=google_artifact_registry_repository.app
```

Review the plan before applying. This enables required APIs and creates the image repository; no GCP environment needs to be deployed to build the API container.

## Step 4: Build and deploy the API

From `backend`, build and push the API image (replace the project, region, and tag values):

```bash
gcloud auth configure-docker REGION-docker.pkg.dev
docker build --platform linux/amd64 -f api/Dockerfile.gcp \
  -t REGION-docker.pkg.dev/PROJECT_ID/alex-app/api:dev .
docker push REGION-docker.pkg.dev/PROJECT_ID/alex-app/api:dev
```

Set `api_image_url` to that exact image URL in `terraform.tfvars`. Then deploy only the API service to obtain its URL:

```bash
cd terraform_gcp/7_frontend
terraform apply -target=google_cloud_run_v2_service.api
terraform output api_url
```

The API Cloud Run service is publicly invokable so the browser can reach it; every user API route still requires a verified Clerk token, and the CORS allowlist is restricted to the configured frontend origin. Its service account uses the Cloud SQL connector and the Secret Manager database password. The Layer 6 stack grants it topic-scoped Pub/Sub publish access.

## Step 5: Build and deploy the frontend

Build the Next.js standalone image from `frontend`, using the API URL returned above and the public Clerk key from `terraform.tfvars`:

```bash
cd frontend
docker build --platform linux/amd64 -f Dockerfile.gcp \
  --build-arg NEXT_PUBLIC_API_URL=https://YOUR_API_SERVICE_URL \
  --build-arg NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_REPLACE_ME \
  -t REGION-docker.pkg.dev/PROJECT_ID/alex-app/frontend:dev .
docker push REGION-docker.pkg.dev/PROJECT_ID/alex-app/frontend:dev
```

Set `frontend_image_url` to the pushed image path in Terraform, then apply the full stack:

```bash
cd terraform_gcp/7_frontend
terraform apply
terraform output frontend_url
```

Copy the exact `frontend_url` output into `frontend_origin` in `terraform.tfvars` (scheme and host only, no trailing slash) and apply again. This sets the API CORS allowlist to the frontend's exact HTTPS origin. The frontend is a Cloud Run Next.js standalone service; this avoids assuming that every Next.js route can be served from a static Cloud Storage bucket. The AWS build still defaults to static export.

## Step 6: Verify production behavior

Check:

1. HTTPS and Clerk sign-in/sign-up redirect behavior.
2. API rejects missing, expired, malformed, and wrong-issuer JWTs.
3. User A cannot access User B's accounts, positions, or jobs.
4. API CORS allows only the configured frontend origin.
5. Account CRUD and analysis-job status work.
6. Starting analysis publishes only the new job ID to Pub/Sub; Planner processes it and persists results.
7. Cloud Logging contains useful request IDs but no credentials or unnecessary financial payloads.

## Troubleshooting

- **401 responses:** inspect token issuer/audience, JWKS URL, clock, and Clerk environment; do not disable JWT checks.
- **CORS errors:** set `frontend_origin` to the exact deployed frontend URL and re-apply the Terraform stack.
- **Cloud Run API is unreachable:** confirm its public `roles/run.invoker` binding is allowed by the organization's IAM policy.
- **Analysis job is not queued:** check the API Cloud Run logs, `PUBSUB_TOPIC`, and the `alex-api` topic-scoped publisher binding from Guide 6.
- **Analysis remains pending:** check Pub/Sub delivery, Planner identity, Cloud Run logs, and Cloud SQL status.
- **Missing secret in browser:** server-side secret keys must never be exposed through client bundles.

## Cost and cleanup

Monitor Cloud Run, load balancer/CDN, network egress, Cloud SQL, and Vertex AI charges. Delete development frontend/API services and resources when no longer needed, preserving production data and required logs:

```bash
cd terraform_gcp/7_frontend
terraform destroy
```

This does not remove the Layer 6 Pub/Sub and agents or the Cloud SQL database.

## Next

Continue to [8_enterprise.md](8_enterprise.md) for monitoring, security, and AI guardrails.
