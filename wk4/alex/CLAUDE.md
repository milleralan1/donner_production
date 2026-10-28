# Alex project guidance

Google Cloud is the only supported deployment target. Start with [`README.md`](README.md) and follow [`guides_GCP/README.md`](guides_GCP/README.md) in order. AWS guides and Terraform under `guides/` and `terraform/` are retired historical references; do not use them to deploy or modify infrastructure. GCP Terraform stacks are under `terraform_gcp/` for Guides 5-8; Guides 1-4 use the documented GCP console and `gcloud` workflows.

Help the student diagnose before changing code: establish their guide, goal, exact command, and error/log output; identify and verify the root cause; then make a focused change and test it. Check GCP project, region, billing, IAM, enabled APIs, `terraform.tfvars`, and deployed resource state before assuming a code defect. Never deploy or destroy live cloud resources without explicit user authorization.

Use `uv` for Python environments and commands. Check costs regularly; Cloud SQL, Vertex AI Vector Search, Cloud Run, and external model providers can incur charges. Never commit credentials, service-account keys, `.env` files, or Terraform state.
