# Alex on Google Cloud

This is the canonical and only supported deployment guide set for Alex. Follow the sequence below; the AWS guides in `../guides` are retired historical material.

## Deployment status

The supported application path uses Cloud SQL for relational data and `pgvector` semantic search, a shared OpenAI-compatible LLM factory (Hugging Face by default, with Nscale supported), configurable Nscale or Vertex AI embeddings, Cloud Run, Pub/Sub, Artifact Registry, Clerk, and Cloud Monitoring. Terraform stacks are provided for Guides 5-8. Complete Guide 5 before Guide 3 because ingestion and vector search use Cloud SQL; do not use the retired AWS Terraform or deployment scripts.

The repository includes focused tests, but live provisioning and end-to-end deployment must be verified in your own GCP project. Never put credentials in source control or commit local Terraform state.

## Guide sequence

| Guide | Topic | Google Cloud services |
|---|---|---|
| [1_permissions.md](1_permissions.md) | Project, billing, IAM, APIs | Cloud IAM, gcloud |
| [2_embeddings.md](2_embeddings.md) | Embedding model | Nscale or Vertex AI |
| [5_database.md](5_database.md) | Relational data and pgvector | Cloud SQL for PostgreSQL, Secret Manager |
| [3_ingest.md](3_ingest.md) | Ingestion and semantic search | Cloud Run, Cloud SQL with pgvector |
| [4_researcher.md](4_researcher.md) | Research agent | Cloud Run, selected LLM provider, Cloud Scheduler |
| [6_agents.md](6_agents.md) | Agent orchestra | Cloud Run, Pub/Sub, Artifact Registry |
| [7_frontend.md](7_frontend.md) | Web app and API | Cloud Run |
| [8_enterprise.md](8_enterprise.md) | Security, monitoring, guardrails | Cloud Monitoring, Cloud Logging, Cloud Armor |
| [architecture.md](architecture.md) | System architecture | GCP service map |
| [agent_architecture.md](agent_architecture.md) | Agent behavior and communication | Provider-neutral agent design |

Complete the guides in the listed order. Create a GCP project with billing and budgets before enabling billable services; check current pricing and quotas in your chosen region. Cloud SQL, Cloud Run, and external LLM provider usage can incur costs. `pgvector` runs inside Cloud SQL and does not create a separate managed vector-search endpoint.
