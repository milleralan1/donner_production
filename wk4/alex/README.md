# Alex - Agentic Learning Equities Explainer

Alex is a multi-agent financial planning learning project. **Google Cloud is the only supported deployment target.** AWS deployment code, Terraform, and the original AWS guides are retained only as retired historical references; do not use them to deploy or modify live resources.

## Start here

Follow the [Google Cloud deployment guides](guides_GCP/README.md) in order. They cover project setup, Vertex AI embeddings, ingestion and vector search, the research agent, Cloud SQL, the agent orchestra, the web app/API, and enterprise monitoring.

The canonical GCP infrastructure is under `terraform_gcp/`. Some early guide resources are configured with `gcloud` because model and vector-index settings depend on the selected region and model; use the exact GCP guide instructions. The old `terraform/` configurations are retired and must not be applied.

## Project directories

- `backend/` - Python services and agents, managed with `uv`
- `frontend/` - Next.js application with Clerk authentication
- `guides_GCP/` - supported deployment instructions
- `terraform_gcp/` - GCP Terraform stacks for database, agents, frontend/API, and enterprise monitoring
- `guides/` and `terraform/` - retired AWS reference material
- `scripts/` - local development and GCP deployment helpers

Set billing alerts and review Google Cloud costs regularly. Cloud SQL, Vertex AI Vector Search, Cloud Run, network egress, and model usage can incur charges. Destroy development resources when they are not in use, while protecting any data you need to retain.