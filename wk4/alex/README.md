# Alex - Agentic Learning Equities Explainer

Alex is a multi-agent financial planning learning project. **Google Cloud is the only supported deployment target.** AWS deployment code, Terraform, and the original AWS guides are retained only as retired historical references; do not use them to deploy or modify live resources.

## Start here

Follow the [Google Cloud deployment guides](guides_GCP/README.md) in order. They cover project setup, embedding providers, Cloud SQL with `pgvector`, ingestion and semantic search, the research agent, the agent orchestra, the web app/API, and enterprise monitoring.

The canonical GCP infrastructure is under `terraform_gcp/`. Some guide resources are configured with `gcloud`; use the exact GCP guide instructions. The old `terraform/` configurations are retired and must not be applied.

## Project directories

- `backend/` - Python services and agents, managed with `uv`
- `frontend/` - Next.js application with Clerk authentication
- `guides_GCP/` - supported deployment instructions
- `terraform_gcp/` - GCP Terraform stacks for database, agents, frontend/API, and enterprise monitoring
- `guides/` and `terraform/` - retired AWS reference material
- `scripts/` - local development and GCP deployment helpers

Set billing alerts and review Google Cloud costs regularly. Cloud SQL, Cloud Run, network egress, and model usage can incur charges. `pgvector` runs inside Cloud SQL and does not create a separately billed vector-search endpoint. Destroy development resources when they are not in use, while protecting any data you need to retain.