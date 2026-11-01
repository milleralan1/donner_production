# Building Alex: Part 4 - Researcher Agent on Cloud Run

Deploy the Researcher as a containerized Cloud Run service. It performs market research using the OpenAI Agents SDK and Nscale's OpenAI-compatible API with `openai/gpt-oss-120b`, then sends its findings through the GCP ingestion path from [Guide 3](3_ingest.md). Embeddings use the provider configured in Guide 2.

## Prerequisites

- Completed Guides 1-3 and 5
- Docker running
- An Nscale API token stored in Secret Manager
- The IAM-protected Cloud Run ingestion service from Guide 3 deployed and accepting authorized calls

## Step 1: Configure the model and runtime identity

The Researcher uses the shared LLM factory at `backend/gcp_agents/gcp_agents/huggingface_model.py`, also used by the five agent services. Provider endpoints, API-key environment names, and default model IDs live in `llm_config.json`; Terraform reads the same file for the five-agent stack. This deployment uses Nscale and `openai/gpt-oss-120b`. Verify that the model currently supports the Agents SDK tool-calling workflow, and check Nscale access, quotas, and pricing.

Configure the GCP-specific service with:

```text
ALEX_LLM_PROVIDER=nscale
ALEX_LLM_MODEL=openai/gpt-oss-120b
NSCALE_API_KEY=provided-from-Secret-Manager-at-runtime
ALEX_INGESTION_URL=https://YOUR_INGESTION_SERVICE.run.app
RESEARCH_TENANT_ID=public_research
```

If `alex-nscale-token` does not already exist, create it and add a version without placing the token in shell history:

```bash
gcloud secrets create alex-nscale-token --replication-policy=automatic \
  --project YOUR_PROJECT_ID
read -s NSCALE_API_KEY
printf '%s' "$NSCALE_API_KEY" | gcloud secrets versions add alex-nscale-token \
  --data-file=- --project YOUR_PROJECT_ID
unset NSCALE_API_KEY
```

Grant the Researcher runtime identity access to the Nscale secret and `roles/run.invoker` on the ingestion service only. ADC is required to mint an ID token for authenticated calls to the ingestion service; this IAM protection does not make its HTTPS URL network-private. The ingestor uses the embedding provider selected in Guide 2 and stores/searches embeddings in Cloud SQL with `pgvector`.

```bash
gcloud iam service-accounts create alex-researcher \
  --project YOUR_PROJECT_ID \
  --display-name "Alex GCP Researcher runtime"

gcloud secrets add-iam-policy-binding alex-nscale-token \
  --project YOUR_PROJECT_ID \
  --member="serviceAccount:alex-researcher@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

gcloud run services add-iam-policy-binding YOUR_INGESTION_SERVICE \
  --region YOUR_REGION \
  --member="serviceAccount:alex-researcher@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/run.invoker"
```

The ingestion URL is also used as the ID token audience by default. If the ingestion service has a custom audience, set `ALEX_INGESTION_AUDIENCE` to that configured audience. For local calls to the IAM-protected ingestion service, use ADC capable of minting an ID token for a service account granted `roles/run.invoker`; do not grant unauthenticated access just to simplify testing.

The GCP service stores scheduled/general research in a fixed `RESEARCH_TENANT_ID` namespace, defaulting to `public_research`, rather than accepting a tenant from the model or request body.

Review the Playwright/browser setup in the Docker image. Headless browsers need compatible OS libraries, resource limits, and a security review; do not grant the container privileged access.

## Step 2: Build and publish the container

Install dependencies and test the GCP-specific entrypoint:

```bash
cd backend/researcher
uv sync
uv run test_gcp_researcher.py
```

If the repository does not already exist, create it. Then authenticate Docker and build and push the image:

```bash
# Run only if the repository does not already exist:
gcloud artifacts repositories create alex-researcher --repository-format=docker --location YOUR_REGION --project YOUR_PROJECT_ID
gcloud auth configure-docker YOUR_REGION-docker.pkg.dev
cd ..
docker build --platform linux/amd64 -f researcher/Dockerfile.gcp -t YOUR_REGION-docker.pkg.dev/YOUR_PROJECT_ID/alex-researcher/researcher:dev .
docker push YOUR_REGION-docker.pkg.dev/YOUR_PROJECT_ID/alex-researcher/researcher:dev
```

The GCP image runs as a non-root user, installs Playwright Chromium, and does not include the AWS Lambda Web Adapter. The Playwright MCP browser runs without disabling Chromium's sandbox.

For local development, run the GCP app using its uv environment and valid GCP ADC:

```bash
uv run uvicorn gcp_server:app --host 127.0.0.1 --port 8080
```

The retired AWS deployment script and Dockerfile are not used in this workflow.

Example Cloud Run deployment after pushing the image:

```bash
gcloud run deploy alex-researcher \
  --image YOUR_REGION-docker.pkg.dev/YOUR_PROJECT_ID/alex-researcher/researcher:dev \
  --region YOUR_REGION \
  --service-account alex-researcher@YOUR_PROJECT_ID.iam.gserviceaccount.com \
  --no-allow-unauthenticated \
  --cpu 2 \
  --memory 2Gi \
  --concurrency 1 \
  --timeout 900 \
  --set-env-vars ALEX_LLM_PROVIDER=nscale,ALEX_LLM_MODEL=openai/gpt-oss-120b,ALEX_INGESTION_URL=https://YOUR_INGESTION_SERVICE.run.app,RESEARCH_TENANT_ID=public_research \
  --set-secrets NSCALE_API_KEY=alex-nscale-token:latest
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

From the repository root, run the verification script after granting your active Google user `roles/run.invoker` on both `alex-researcher` and `alex-ingestion`:

```bash
chmod +x guides_GCP/scripts/verify_researcher.zsh
./guides_GCP/scripts/verify_researcher.zsh
```

The script starts authenticated local proxies for both services, checks API reachability, submits a bounded research request, and searches for its result in the `public_research` tenant. The research request calls Nscale and uses browser tools, so it may incur provider and Cloud Run charges and writes a document to the ingestion database. Review the output and Cloud Run logs; confirm the service:

1. Invokes the configured Nscale `openai/gpt-oss-120b` model within the account's current quota.
2. Uses browser tools only for allowed destinations and handles untrusted web content as data.
3. Sends the research document to the GCP ingestion API.
4. Returns a clear response and does not log secrets or sensitive user data.
5. Produces searchable results from the deployed vector service.

Use Cloud Run logs in Cloud Logging to diagnose startup, browser, model permission, quota, and downstream API issues.

Set `ALEX_RESEARCH_TOPIC` to change the research prompt, `RESEARCH_TENANT_ID` to change the search tenant, `ALEX_RESEARCH_TIMEOUT_SECONDS` to change the request timeout, or `ALEX_RESEARCHER_PROXY_PORT` / `ALEX_INGESTION_PROXY_PORT` if the default local ports are in use.

## Step 4: Optional scheduled research

Use Cloud Scheduler to call the research endpoint on a schedule. Configure an OIDC token using a dedicated scheduler service account and grant it `roles/run.invoker` on the specific Cloud Run service. Start with scheduling disabled; enable only after manual requests work and costs are understood.

Monitor Cloud Scheduler job status and Cloud Run request/error logs. Disable or delete the schedule to stop automated model and browsing charges.

## Troubleshooting

- **Container fails to start:** inspect Cloud Run startup logs, container port, dependencies, and browser libraries.
- **Provider authentication, model, or rate-limit errors:** verify `ALEX_LLM_PROVIDER=nscale`, `ALEX_LLM_MODEL=openai/gpt-oss-120b`, the `NSCALE_API_KEY` secret binding and Secret Manager access/version, and that the model supports the needed features.
- **Ingestion unauthorized:** check the service-to-service identity and target invoker permissions; do not grant unauthenticated access as a shortcut.
- **Timeouts:** inspect browser duration and service timeout; bound tool work rather than raising limits without evidence.

## Cleanup

Delete the Cloud Scheduler job and Cloud Run service when not in use. Remove unused Artifact Registry images if appropriate. Nscale inference is hosted externally, so there is no GCP model endpoint to delete; monitor Nscale usage and GCP Cloud Run/browser costs.

## Next

Continue to [6_agents.md](6_agents.md) to deploy the agent orchestra.
