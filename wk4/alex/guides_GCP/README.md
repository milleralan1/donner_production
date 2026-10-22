# Alex on Google Cloud

This guide set describes a Google Cloud deployment path for Alex, following the same eight-part learning sequence as [`../guides`](../guides).

## Migration status

The original AWS implementation remains available. GCP implementations now include Cloud SQL persistence and provisioning, Groq text generation for the Researcher and five-agent orchestra, Vertex AI embeddings and ingestion/search, the Cloud Run API/frontend deployment path, and Layer 8 Monitoring infrastructure and GCP frontend security headers. All eight code/infrastructure layers are represented; live GCP provisioning, alert delivery, and end-to-end deployment validation remain dependent on the student's project and credentials.

Do not run AWS Terraform or copy AWS commands from the original guides expecting them to deploy on GCP. GCP deployment requires its own infrastructure and service configuration. Never put credentials in source control or commit local Terraform state.

## Guide sequence

| Guide | Topic | Google Cloud services |
|---|---|---|
| [1_permissions.md](1_permissions.md) | Project, billing, IAM, APIs | Cloud IAM, gcloud |
| [2_embeddings.md](2_embeddings.md) | Embedding model | Vertex AI |
| [3_ingest.md](3_ingest.md) | Ingestion and semantic search | Cloud Run, Cloud Storage, Vertex AI Vector Search |
| [4_researcher.md](4_researcher.md) | Research agent | Cloud Run, Groq, Cloud Scheduler |
| [5_database.md](5_database.md) | Relational data | Cloud SQL for PostgreSQL, Secret Manager |
| [6_agents.md](6_agents.md) | Agent orchestra | Cloud Run, Pub/Sub, Artifact Registry |
| [7_frontend.md](7_frontend.md) | Web app and API | Cloud Storage/CDN or Cloud Run, API Gateway |
| [8_enterprise.md](8_enterprise.md) | Security, monitoring, guardrails | Cloud Monitoring, Cloud Logging, Cloud Armor |
| [architecture.md](architecture.md) | System architecture | GCP service map |
| [agent_architecture.md](agent_architecture.md) | Agent behavior and communication | Provider-neutral agent design |

Complete the guides in order. Create a GCP project with billing and budgets before enabling billable services; check current pricing and quotas in your chosen region. Cloud SQL, Vertex AI Vector Search, browser-enabled Cloud Run services, and Groq usage can incur costs; Groq free-tier limits change and are not unlimited. Stop or delete billable resources when not actively using them. Unit tests use mocks; deployment and live GCP connectivity still require provisioned resources and IAM.
