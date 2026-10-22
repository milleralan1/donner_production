# Building Alex: Part 4 - Researcher Agent on Cloud Run

Deploy the Researcher as a containerized Cloud Run service. It performs market research using the OpenAI Agents SDK and Groq through LiteLLM, then sends its findings through the GCP ingestion path from [Guide 3](3_ingest.md). Vertex AI remains in use for embeddings and vector search, not text generation.

## Important migration note

The AWS `server.py`, `tools.py`, Dockerfile, and deployment script remain AWS-specific. The GCP implementation is separate in `backend/researcher/gcp_server.py` and `gcp_tools.py`, with a GCP-only `Dockerfile.gcp`; the AWS deployment path is unchanged.

## Prerequisites

- Completed Guides 1-3
- Docker running
- A Groq account, API key, and a model that supports tool calling
- The Groq API key stored in Secret Manager
- The private Cloud Run ingestion service from Guide 3 deployed and accepting authorized calls

## Step 1: Configure the model and runtime identity

Choose a Groq model that supports tool calling and is available to your account. Check current model availability, free-tier quotas, and rate limits in the Groq console; free access is limited and can change. LiteLLM uses the `groq/` model prefix.

Configure the GCP-specific service with:

```text
GROQ_API_KEY=provided-from-Secret-Manager-at-runtime
RESEARCHER_MODEL=groq/llama-3.3-70b-versatile
ALEX_INGESTION_URL=https://YOUR_INGESTION_SERVICE.run.app
RESEARCH_TENANT_ID=public_research
```

If the secret does not already exist, create it and add a version without putting the key in shell history:

```bash
# Skip the create command if this secret already exists.
gcloud secrets create alex-groq-api-key --replication-policy=automatic \
  --project YOUR_PROJECT_ID
read -s GROQ_API_KEY
printf '%s' "$GROQ_API_KEY" | gcloud secrets versions add alex-groq-api-key \
  --data-file=- --project YOUR_PROJECT_ID
unset GROQ_API_KEY
```

Grant the Researcher runtime identity access to this secret and `roles/run.invoker` on the ingestion service only. ADC is still required for authenticated calls to the private ingestion service; the ingestor separately uses Vertex AI for embeddings.

```bash
gcloud iam service-accounts create alex-researcher \
  --project YOUR_PROJECT_ID \
  --display-name "Alex GCP Researcher runtime"

gcloud secrets add-iam-policy-binding alex-groq-api-key \
  --project YOUR_PROJECT_ID \
  --member="serviceAccount:alex-researcher@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

gcloud run services add-iam-policy-binding YOUR_INGESTION_SERVICE \
  --region YOUR_REGION \
  --member="serviceAccount:alex-researcher@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/run.invoker"
```

The ingestion URL is also used as the ID token audience by default. If the ingestion service has a custom audience, set `ALEX_INGESTION_AUDIENCE` to that configured audience. For local calls to the private ingestion service, use ADC capable of minting an ID token for a service account granted `roles/run.invoker`; never make the service public just to simplify testing.

The GCP service stores scheduled/general research in a fixed `RESEARCH_TENANT_ID` namespace, defaulting to `public_research`, rather than accepting a tenant from the model or request body.

Review the Playwright/browser setup in the Docker image. Headless browsers need compatible OS libraries, resource limits, and a security review; do not grant the container privileged access.

## Step 2: Build and publish the container

Install the GCP dependency extra and test the GCP-specific entrypoint:

```bash
cd backend/researcher
uv sync --extra gcp
uv run test_gcp_researcher.py
```

Create an Artifact Registry Docker repository in the deployment region, then build and push the separate GCP image:

```bash
gcloud builds submit \
  --tag YOUR_REGION-docker.pkg.dev/YOUR_PROJECT_ID/alex/researcher:dev \
  --file Dockerfile.gcp .
```

The GCP image runs as a non-root user, installs Playwright Chromium, and does not include the AWS Lambda Web Adapter. The Playwright MCP browser runs without disabling Chromium's sandbox.

For local development, run the GCP app using its uv environment and valid GCP ADC:

```bash
uv run uvicorn gcp_server:app --host 127.0.0.1 --port 8080
```

The existing AWS `deploy.py` and `Dockerfile` are not part of this workflow.

Example Cloud Run deployment after pushing the image:

```bash
gcloud run deploy alex-researcher \
  --image YOUR_REGION-docker.pkg.dev/YOUR_PROJECT_ID/alex/researcher:dev \
  --region YOUR_REGION \
  --service-account alex-researcher@YOUR_PROJECT_ID.iam.gserviceaccount.com \
  --no-allow-unauthenticated \
  --cpu 2 \
  --memory 2Gi \
  --concurrency 1 \
  --timeout 900 \
  --set-env-vars RESEARCHER_MODEL=groq/llama-3.3-70b-versatile,ALEX_INGESTION_URL=https://YOUR_INGESTION_SERVICE.run.app,RESEARCH_TENANT_ID=public_research \
  --set-secrets GROQ_API_KEY=alex-groq-api-key:latest
```

Use a pinned image digest for repeatable deployments. Start with zero minimum instances and bounded concurrency; browser processes can use material memory/CPU.

Grant the Cloud Run invoker role on the researcher service to the intended calling identity. For optional Cloud Scheduler invocation, give the scheduler identity `roles/run.invoker` on this service and configure OIDC with the service URL as audience. Keep scheduling disabled until manual invocation works.

Example authenticated invocation:

```bash
gcloud run services proxy alex-researcher --region YOUR_REGION
```

Then, in another terminal:

```bash
curl -X POST http://localhost:8080/research \
  -H "Content-Type: application/json" \
  -d '{"topic":"long-term bond ETF market trends"}'
```

The proxy authenticates the caller with your gcloud identity. Do not expose the service publicly for testing.

The service liveness endpoint is `GET /healthz`; it does not make paid model or browser calls.

## Step 3: Validate the end-to-end flow

Test the health endpoint, then request research on a bounded topic. Confirm the service:

1. Invokes the configured Groq model within the account's current quota.
2. Uses browser tools only for allowed destinations and handles untrusted web content as data.
3. Sends the research document to the GCP ingestion API.
4. Returns a clear response and does not log secrets or sensitive user data.
5. Produces searchable results from the deployed vector service.

Use Cloud Run logs in Cloud Logging to diagnose startup, browser, model permission, quota, and downstream API issues.

## Step 4: Optional scheduled research

Use Cloud Scheduler to call the research endpoint on a schedule. Configure an OIDC token using a dedicated scheduler service account and grant it `roles/run.invoker` on the specific Cloud Run service. Start with scheduling disabled; enable only after manual requests work and costs are understood.

Monitor Cloud Scheduler job status and Cloud Run request/error logs. Disable or delete the schedule to stop automated model and browsing charges.

## Troubleshooting

- **Container fails to start:** inspect Cloud Run startup logs, container port, dependencies, and browser libraries.
- **Groq authentication, model, or rate-limit errors:** verify the Secret Manager version, model ID, account access, and current quota.
- **Ingestion unauthorized:** check the service-to-service identity and target invoker permissions; do not make the ingestion service public as a shortcut.
- **Timeouts:** inspect browser duration and service timeout; bound tool work rather than raising limits without evidence.

## Cleanup

Delete the Cloud Scheduler job and Cloud Run service when not in use. Remove unused Artifact Registry images if appropriate. Groq is an external API, so there is no GCP model endpoint to delete; monitor Groq account usage and GCP Cloud Run/browser costs.

## Next

Continue to [5_database.md](5_database.md) to provision Cloud SQL for PostgreSQL.
