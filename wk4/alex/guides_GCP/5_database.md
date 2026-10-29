# Building Alex: Part 5 - Cloud SQL and Shared Database

This guide maps Aurora Serverless v2 and its Data API to Cloud SQL for PostgreSQL. Cloud SQL is a managed relational database, but it does **not** provide Aurora Data API behavior or automatically scale to zero. Plan connectivity, credentials, backups, and ongoing costs before creating an instance.

## What you'll build

- A Cloud SQL for PostgreSQL instance and the `alex` database
- Secret Manager storage for database credentials
- A private, authenticated application-to-database connection
- The existing schema, migrations, seed data, and shared database models

## Prerequisites

- Completed Guides 1 and 2
- Cloud SQL Admin API and Secret Manager API enabled
- A GCP runtime service account
- Read the existing schema at `backend/database/migrations/001_schema.sql`

## Step 1: Choose connectivity and cost settings

For a learning deployment, Cloud Run can connect to Cloud SQL using the Cloud SQL connector/Cloud Run integration and a service account with `roles/cloudsql.client`. Select a supported connectivity configuration and follow current Cloud SQL guidance. Private IP requires appropriate VPC connectivity; do not assume the AWS Data API's HTTP/no-VPC pattern exists on GCP.

Choose a small development machine tier, storage, backup settings, availability, and region deliberately. Cloud SQL generally has ongoing instance costs while running; it is not equivalent to pausable Aurora Serverless v2. Check pricing and consider deleting the development instance when finished, after taking any needed backup.

## Step 2: Provision database and credentials

Create the runtime identities and enable the required APIs:

```bash
gcloud services enable sqladmin.googleapis.com secretmanager.googleapis.com
gcloud iam service-accounts create alex-api --project YOUR_PROJECT_ID
gcloud iam service-accounts create alex-agents --project YOUR_PROJECT_ID
gcloud iam service-accounts create alex-ingestion --project YOUR_PROJECT_ID
```

The separate GCP Terraform stack in `terraform_gcp/5_database` provisions PostgreSQL, the `alex` database, an application user, a generated password in Secret Manager, and scoped IAM grants for the listed runtime identities. Include all service accounts that need database access (including `alex-ingestion`) in `runtime_service_accounts`. Review the defaults and regional pricing before applying. It defaults to a development-tier instance and deletion protection.

```bash
cd terraform_gcp/5_database
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your project, region, and service account emails.
terraform init
terraform validate
terraform plan
terraform apply
```

Terraform state contains the generated database password even though it is marked sensitive and never output. Keep local state private, never commit it, and use an access-controlled remote backend for shared or production use. The stack enables both Terraform's deletion guard and Cloud SQL's server-side deletion protection. Set `deletion_protection = false` in the local tfvars before intentionally destroying the instance.

Terraform grants the Cloud Run and agent runtime identities `roles/cloudsql.client` and access to only the database password secret. Use the generated least-privilege application database user rather than a PostgreSQL superuser for application queries.

## Step 3: Configure and test the connection layer

The supported database package uses Cloud SQL. Set `DATABASE_BACKEND=cloud_sql` in each service environment that uses the database (API and agents) and install the GCP extra in those environments and in `backend/database` for database scripts:

```bash
uv sync --extra gcp
```

Set the following configuration in the service environment. In production, inject `DB_PASSWORD` from Secret Manager rather than storing it in source control or a committed `.env` file.

```text
DATABASE_BACKEND=cloud_sql
CLOUD_SQL_CONNECTION_NAME=PROJECT_ID:REGION:INSTANCE_NAME
CLOUD_SQL_IP_TYPE=PUBLIC
DB_NAME=alex
DB_USER=alex_app
DB_PASSWORD=INJECT_FROM_SECRET_MANAGER
```

For Cloud Run, map the Terraform-created secret to `DB_PASSWORD` and configure the connection name returned by Terraform:

```bash
gcloud run services update YOUR_CLOUD_RUN_SERVICE \
  --region YOUR_REGION \
  --update-env-vars DATABASE_BACKEND=cloud_sql,CLOUD_SQL_CONNECTION_NAME=PROJECT_ID:REGION:INSTANCE_NAME,CLOUD_SQL_IP_TYPE=PUBLIC,DB_NAME=alex,DB_USER=alex_app \
  --update-secrets DB_PASSWORD=alex-cloud-sql-password:latest
```

If you changed `password_secret_id`, use that secret ID instead. The service account must be one of the identities in `runtime_service_accounts`.

Use `CLOUD_SQL_IP_TYPE=PRIVATE` only when the runtime has a VPC path to the instance. The connector uses Application Default Credentials: locally run `gcloud auth application-default login`; in Cloud Run, use a dedicated runtime service account with `roles/cloudsql.client` and access only to the database password secret. Do not pass AWS ARNs or invoke `rds-data`.

The GCP client preserves the current model/client response contract so application queries can continue using the shared models. It translates named parameters (including PostgreSQL casts such as `:id::uuid`) to driver parameters. Keep SQL parameterized and preserve Clerk user IDs as tenant identifiers. Connections are opened per operation; keep Cloud Run instance counts/concurrency aligned with Cloud SQL connection limits.

## Step 4: Install extensions, then apply migrations and seed data

Cloud SQL extensions must be installed by a user with the `cloudsqlsuperuser` role. In Cloud SQL Studio, connect to the `alex` database as the `postgres` user and run:

```sql
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS vector;
```

The application user does not need extension-creation privileges. Then run migrations with the configured database application user; migration `002_pgvector.sql` creates the research-document table and grants table access to `alex_app`. If you selected a different `database_user` in Terraform, change the grant target in that migration before running it. Keep the schema and seed data where provider-independent. Review migrations for PostgreSQL-version differences and verify they complete before enabling application traffic.

```bash
cd backend/database
uv sync --extra gcp
uv run test_cloud_sql.py
uv run run_migrations.py
uv run seed_data.py
uv run seed_pgvector.py
uv run verify_database.py
```

Before running `seed_pgvector.py`, set `EMBEDDING_OUTPUT_DIMENSIONALITY` to the verified dimension from Guide 2. The script inserts three deterministic, synthetic vectors under the isolated `alex-pgvector-seed` tenant to check vector storage and cosine-distance queries; these are not semantic embeddings and are not intended for application search. `verify_database.py` checks the extension, vector column, stored dimensions, smoke-test rows, and cosine-distance operator.

The migration, seed, verification, and reset scripts use `DATABASE_BACKEND` like the application. Use `test_cloud_sql.py` for Cloud SQL connectivity. The connectivity test requires the deployed instance, ADC, and the environment below. Do not run destructive reset scripts against a database containing data you need.

## Step 5: Verify application data isolation

Check table counts, foreign keys, indexes, and allocation totals. Create test data only in a development project. Verify every user-facing query scopes by the authenticated Clerk user ID; a shared database does not provide tenant isolation automatically.

## Troubleshooting

- **Connection refused or timeout:** verify Cloud Run-to-Cloud SQL configuration, instance state, VPC/private IP path, and connection name.
- **IAM denial:** confirm the actual Cloud Run runtime service account has Cloud SQL Client and secret access.
- **Too many connections:** lower Cloud Run concurrency/maximum instances or configure a suitable pool; do not mask the issue by granting elevated database roles.
- **Migration failure:** inspect the first SQL error and database version; take a backup before retrying destructive changes.

## Cost and cleanup

Monitor Cloud SQL instance, storage, backup, and network charges. Back up any data you need, then delete the instance deliberately to stop ongoing compute charges. Retain or delete backups according to your data-retention requirements.

## Next

Continue to [3_ingest.md](3_ingest.md) to deploy ingestion and semantic search on Cloud Run.
