# Retired AWS Terraform

**AWS is no longer a supported deployment target.** Do not use the configurations in this directory to create or update infrastructure. The legacy stacks are retained only for historical reference and existing-resource cleanup.

Every stack has a `retired_aws_acknowledgement` variable that defaults to `false` and prevents planning until explicitly acknowledged. To inspect or clean up an existing AWS stack only, pass `-var=retired_aws_acknowledgement=true` to the Terraform command. Do not use that override for new deployments.

Use the supported GCP stacks in [`../terraform_gcp`](../terraform_gcp) and follow [`../guides_GCP/README.md`](../guides_GCP/README.md). Guides 1-4 use GCP console/CLI workflows; Terraform stacks are provided for Guides 5-8.
