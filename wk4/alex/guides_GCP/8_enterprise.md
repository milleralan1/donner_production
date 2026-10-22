# Guide 8: Enterprise Features on Google Cloud

This final guide maps Alex's scalability, security, monitoring, guardrails, explainability, and observability practices to Google Cloud. The GCP Monitoring stack and frontend security headers are implemented separately from AWS. No cloud resources are created until you review and apply the Terraform configuration.

## 1. Scale deliberately

Cloud Run scales stateless services based on demand; set maximum instances, concurrency, CPU/memory, request timeouts, and minimum instances based on measured load. Use Cloud Run Jobs for bounded batch work. Pub/Sub decouples requests from agent processing and supports retries, but delivery is at-least-once, so handlers must be idempotent.

Cloud SQL and Vertex AI Vector Search have capacity and cost behavior distinct from Aurora Serverless and S3 Vectors. Load-test in a non-production project, watch database connection limits and model quotas, and increase capacity only after identifying the bottleneck. Use Cloud Armor with an external Application Load Balancer where appropriate; API Gateway alone should not be described as a complete DDoS/WAF control.

## 2. Apply defense in depth

- Use separate service accounts for the API, Planner, each agent, scheduler, and deployment pipeline where practical.
- Grant narrow roles at the resource level. Avoid service-account keys and project-wide Owner/Editor grants.
- Store credentials in Secret Manager and grant accessor permission only to the consuming runtime identity.
- Keep Cloud SQL and internal Cloud Run services private where feasible; use supported connector/networking mechanisms.
- Validate Clerk JWT signature, issuer, audience, expiry, and user identity on the server.
- Configure exact CORS origins, HTTPS, secure browser headers/CSP, request size limits, and rate controls.
- Enable Cloud Audit Logs and review security findings. Consider Security Command Center, Cloud Armor, VPC Service Controls, and organization policies according to threat model, requirements, availability, and cost.

Cloud security products have different coverage and pricing; do not assume a named AWS feature has a one-for-one GCP replacement.

## 3. Deploy Monitoring dashboards and alerts

The independent Terraform stack in `terraform_gcp/8_enterprise` enables Cloud Logging and Cloud Monitoring APIs, creates a log-based metric for error-level messages from Alex Cloud Run services, and provisions a dashboard plus alert policies for Cloud Run errors, Pub/Sub queue backlog/message age, and Cloud SQL CPU. It does not create notification channels or change project-wide IAM, service ingress, or log retention.

Complete Guides 3-7 first so the monitored resources exist. Find the Cloud SQL instance ID from Guide 5 outputs and format it for Monitoring as `PROJECT_ID:INSTANCE_ID`. Create a notification channel in Cloud Monitoring (email is suitable for a learning project), then configure:

```bash
cd terraform_gcp/8_enterprise
cp terraform.tfvars.example terraform.tfvars
```

Set the project, region, Cloud SQL Monitoring resource ID, and any notification channel resource names. Verify `cloud_run_services` and `pubsub_subscription_ids` in `variables.tf` match the resources you deployed. A notification channel ID is a resource name, not an email address. The deployment identity needs permission to enable the two APIs and manage Monitoring and Logging metrics (for example, the appropriate Service Usage, Monitoring, and Logging configuration roles); do not grant these roles to runtime service accounts.

```bash
terraform init
terraform fmt -check
terraform validate
terraform plan
terraform apply
terraform output dashboard_url
terraform output alert_policy_names
```

Review the plan and any notification destinations before applying. Tune thresholds against observed traffic; the included values are starter thresholds, not SLOs. Empty `notification_channel_ids` creates alert policies without delivery destinations.

The dashboard includes Cloud Run request counts and p95 latency, Alex error logs, Pub/Sub backlog and oldest-message age, and Cloud SQL CPU. Metrics can take several minutes to appear. Data Access audit logs are not automatically enabled by this stack; decide whether to enable them after reviewing privacy, retention, and logging costs with your administrator.

## 4. Observe services and costs

Use Cloud Logging for structured application logs and Cloud Monitoring for dashboards, alerting, and service metrics. Include correlation/job IDs and agent names; avoid logging access tokens, API keys, full prompts containing personal data, or raw portfolio records unless a documented need and retention policy exist.

The Terraform stack creates alerts for Cloud Run error logs, Pub/Sub backlog/message age, and Cloud SQL CPU. For a production workload, consider adding alert policies for:

- Cloud Run request errors, latency, instance saturation, and container restarts
- Pub/Sub undelivered/oldest message age and dead-letter messages
- Cloud SQL availability, CPU, storage, connections, and backup failures
- Vertex AI quota/errors and unexpected usage
- Budget thresholds and unusual spending

Set log retention and alert notification channels intentionally. Budgets are notifications, not hard spending caps.

Check a deployed service's logs with:

```bash
gcloud run services list --region YOUR_REGION
gcloud logging read \
  'resource.type="cloud_run_revision" AND resource.labels.service_name="YOUR_SERVICE"' \
  --project YOUR_PROJECT_ID --limit 50
```

## 5. Implement AI guardrails

The API's `AnalyzeRequest` model now limits `analysis_type` to 64 characters and `options` to 32 entries and 16 KiB of serialized JSON. Focused unit tests cover the boundary cases. Continue validating other inputs structurally with Pydantic, enforce domain-specific ranges, and treat retrieved documents and web pages as untrusted data. Prompt-injection keyword filters are not a security boundary; isolate instructions from retrieved content and restrict tools, destinations, and tool permissions.

Validate model output against a typed schema and business rules before persistence or display. On invalid output, surface an explicit error/status and record a safe diagnostic; do not silently return success-shaped empty results. Retry only transient, idempotent operations with bounded exponential backoff.

For financial advice, present limitations and data timestamps, avoid unsupported guarantees, and require appropriate human/product review. Do not expose hidden chain-of-thought. Provide concise user-facing rationale, evidence/data sources, assumptions, and limitations instead.

## 6. Make outputs explainable and auditable

Capture the model/version, prompt/template version, source IDs, validation outcome, duration, and output hash or safe summary. Keep the audit trail proportionate, access-controlled, and subject to retention/privacy requirements. Never log sensitive financial inputs just to make a trace more detailed.

Use clear explanations of observed factors and assumptions, not private reasoning traces. Verify that explanations are consistent with the underlying portfolio data and agent output.

## 7. Add Langfuse or another tracing provider

Langfuse can remain a provider-neutral observability tool. Configure its keys through Secret Manager and instrument supported OpenTelemetry/OpenAI Agents SDK spans. Verify SDK and Vertex AI/LiteLLM compatibility in a local environment first; AWS-specific `observability.py` setup and Bedrock assumptions may need changes. Flush traces before short-lived jobs exit.

Send only data approved for external processing. Redact tokens and sensitive fields, review the tracing provider's data retention and region, and use a self-hosted or approved alternative if required by policy. Langfuse remains optional and is not automatically enabled or given financial data by this Monitoring stack.

## 8. Browser security headers

The GCP standalone Next.js build adds HSTS, `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, and a restrictive `Permissions-Policy`. These headers are served by the Next.js Cloud Run container; the AWS static-export build remains unchanged. CSP is intentionally not set here because Clerk domains and inline Next.js behavior must be verified against the selected Clerk instance before enforcing a policy.

After deployment, inspect response headers for both `/` and a static asset. Cloud Run's public service URL is HTTPS; if you front it with a custom domain or proxy, confirm that endpoint also enforces HTTPS before relying on HSTS.

## 9. Verify the complete system

Run tests that cover authentication, tenant isolation, Pub/Sub duplicate delivery, dead-letter behavior, database failures, model/tool timeouts, invalid structured outputs, and secret redaction. Confirm alerts trigger in a test environment. Review cost dashboards after load tests and remove temporary resources.

Run the new API request guardrail tests without contacting GCP:

```bash
cd backend
uv run --project api --extra gcp python api/test_guardrails.py
```

## 10. Clean up

This stack only manages its dashboard, alert policies, and log-based metric. When no longer needed, remove those resources without destroying the application layers:

```bash
cd terraform_gcp/8_enterprise
terraform destroy
```

Review Cloud Logging and Monitoring retention and current pricing before enabling additional metrics, data access logs, or third-party traces.

## Completion

The original AWS Guide 8 includes Terraform snippets for AWS Lambda, Aurora, API Gateway, WAF, GuardDuty, and CloudWatch. Those snippets are intentionally not reused for GCP. The GCP monitoring Terraform and GCP-only frontend headers are implemented; completing this guide still requires a reviewed Terraform apply, configured alert destinations, and verification in the student's GCP project. The AWS deployment and defaults remain unchanged.
