# Building Alex: Part 2 - Embeddings with Nscale or Vertex AI

Alex uses embeddings to make financial research searchable by meaning. Nscale is the configured embedding provider for the current model migration; Vertex AI remains available as an alternative. Either provider works with the GCP ingestion service, which stores vectors in Cloud SQL using `pgvector`.

## What you'll build

- An embedding provider and model selection
- A verified embedding request and recorded output dimension
- A shared configuration that the ingestion guide can use

## Prerequisites

- Completed [Guide 1](1_permissions.md) before provisioning GCP resources
- An Nscale account, service token, and available inference credits for the Nscale live test; alternatively, Vertex AI API access for that provider
- Python project managed with `uv`

## Step 1: Configure Nscale

The target Nscale model ID is `Qwen/Qwen3-Embedding-8B`. Nscale's serverless inference API exposes embeddings at `https://inference.api.nscale.com/v1/embeddings`. Confirm that the model is enabled for your Nscale account, and check its current limits and pricing in the Nscale console/model catalog. Nscale's public API examples currently show `Qwen3-Embedding-8B` without the `Qwen/` prefix, so use the exact model ID listed for your account if it differs.

For local development, create a private `.env` file in `backend/ingest` with:

```dotenv
EMBEDDING_PROVIDER=nscale
EMBEDDING_MODEL=Qwen/Qwen3-Embedding-8B
NSCALE_API_KEY=YOUR_NSCALE_SERVICE_TOKEN
NSCALE_BASE_URL=https://inference.api.nscale.com/v1
```

`NSCALE_BASE_URL` is optional and defaults to the value shown. `EMBEDDING_OUTPUT_DIMENSIONALITY` is also optional for the standalone test; leave it unset until you make the live request and verify the actual returned size. Never commit `.env` or paste a real token into source control, logs, or command-line arguments.

The Nscale client uses the OpenAI-compatible embeddings API and accepts the existing document/query task labels, but Nscale's API does not expose a retrieval task-type parameter. It therefore sends identical model requests for documents and queries. Evaluate retrieval quality before using the model for production search.

To keep existing Vertex AI embedding deployments, set `EMBEDDING_PROVIDER=vertex_ai` and configure:

```dotenv
EMBEDDING_MODEL=YOUR_SUPPORTED_VERTEX_EMBEDDING_MODEL
GOOGLE_CLOUD_PROJECT=YOUR_PROJECT_ID
GOOGLE_CLOUD_LOCATION=YOUR_VERTEX_EMBEDDING_LOCATION
```

Vertex AI uses Application Default Credentials locally and the Cloud Run service identity in production. Do not put service-account keys in `.env`.

## Step 2: Run local tests

From `backend/ingest`, install dependencies and run the offline tests:

```bash
uv sync
uv run test_vertex_embeddings.py
uv run test_nscale_embeddings.py
uv run test_embedding_client.py
uv run test_gcp_ingestion.py
```

These tests use fake provider responses and mocked GCP services; they make no Nscale or GCP API calls and incur no inference charges.

## Step 3: Verify the live Nscale model and dimension

Load the local `.env` for just this invocation and send one short test input:

```bash
uv run --env-file .env test_nscale_embeddings_live.py
```

This makes one Nscale API request and prints only the returned vector dimension, not the vector or token. It requires a valid service token and may consume Nscale credits. Record the observed dimension and set `EMBEDDING_OUTPUT_DIMENSIONALITY` to that value for ingestion. If testing Vertex AI instead, use ADC (`gcloud auth application-default login`) and `uv run test_vertex_embeddings_live.py`; that makes one billable Vertex AI request.

For the live response, verify:

1. The response contains a non-empty numeric vector.
2. The vector dimension matches the model documentation.
3. The model is available for your Nscale account and input limits are respected.
4. Record the returned dimension and use it consistently for document ingestion and query search.

Do not assume the model's published maximum dimension is the size returned by the service. Ingestion and search must use the same provider, model, and dimension.

## Step 4: Connect the embedding provider to GCP ingestion

The unit tests above verify local behavior without deployed resources. Running ingestion end to end additionally requires the Cloud SQL instance from Guide 5 with the `vector` extension installed. Embeddings are stored and searched in that PostgreSQL database; no Vertex AI Vector Search endpoint is required.

For a deployed Cloud Run ingestion service, bind `NSCALE_API_KEY` from Secret Manager rather than storing it in a Terraform variable or container image. The service uses its Cloud SQL connector identity for database access.

## Step 5: Migration and cost notes

Changing embedding model or provider changes the vector space. Do not mix embeddings from different models in search; re-embed the stored documents before switching the active model.

Nscale serverless inference consumes Nscale credits. Cloud SQL has its normal instance, storage, backup, and network costs; `pgvector` is an extension running inside that instance, not a separately billed vector endpoint. Check provider and Cloud SQL usage before bulk ingestion.

## Next

Continue to [5_database.md](5_database.md) to prepare Cloud SQL for relational data and `pgvector`, then follow Guide 3 for ingestion.
