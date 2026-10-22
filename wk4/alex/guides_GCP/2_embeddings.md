# Building Alex: Part 2 - Vertex AI Embeddings

Alex uses embeddings to make financial research searchable by meaning. On Google Cloud, Vertex AI provides managed embedding models through an API; this is not a SageMaker endpoint and does not use the SageMaker Terraform or AWS runtime client in this repository.

## What you'll build

- A Vertex AI embedding model selection for your region and use case
- A verified embedding request and recorded output dimension
- A shared configuration that the ingestion guide can use

## Prerequisites

- Completed [Guide 1](1_permissions.md)
- Vertex AI API enabled
- A deployment identity with permission to invoke the chosen model
- Python project managed with `uv`

## Step 1: Choose a supported model

Review the Vertex AI model catalog and model card for the chosen region, model availability, input limits, output dimension, and pricing. Use a text embedding model supported for your project (for example, a current Vertex AI text embedding model); do not assume the AWS project's `all-MiniLM-L6-v2` model or its 384 dimensions carry over.

The vector index dimension must exactly match the embedding model's output dimension. Confirm the model's current documented dimension and inspect a real response before creating the index. Model names, dimensions, and regional availability can change.

Set non-secret configuration, for example:

```dotenv
EMBEDDING_PROVIDER=vertex_ai
EMBEDDING_MODEL=YOUR_SUPPORTED_VERTEX_EMBEDDING_MODEL
GOOGLE_CLOUD_PROJECT=YOUR_PROJECT_ID
GOOGLE_CLOUD_REGION=YOUR_REGION
```

Authenticate using ADC locally; on Google Cloud, attach a dedicated service account with Vertex AI invocation access. Do not put service account JSON keys in `.env`.

## Step 2: Test one embedding before provisioning a vector index

The repository includes `backend/ingest/vertex_embeddings.py`, a Vertex AI implementation separate from the existing SageMaker code. Configure the model and project settings from Step 1, then install and test the GCP extra:

```bash
cd backend/ingest
uv sync --extra gcp
uv run test_vertex_embeddings.py
```

The test exercises request validation and the Google Gen AI SDK call with a fake response; it does not incur model charges. To verify real model access, use ADC locally (`gcloud auth application-default login`) and run:

```bash
uv run test_vertex_embeddings_live.py
```

This makes one billable model request and prints only the returned dimension. The client supports `RETRIEVAL_DOCUMENT` and `RETRIEVAL_QUERY` task types and optionally accepts `EMBEDDING_OUTPUT_DIMENSIONALITY`.

For the real response, verify:

1. The response contains a non-empty numeric vector.
2. The vector dimension matches the model documentation.
3. The selected region supports the model.
4. Inputs are within the model's limits and use the expected task type.

Record the verified dimension in configuration used by the vector index. Keep the model and dimension aligned across ingestion and search, including after model changes.

## Step 3: Understand the hosting difference

The AWS path provisions a SageMaker Serverless endpoint and calls SageMaker Runtime. A managed Vertex AI embedding API generally needs no user-created endpoint. It is billed according to the model's pricing and usage; it does not necessarily scale or price exactly like SageMaker Serverless.

If a selected embedding model requires a custom deployed endpoint, follow that model's current Vertex AI deployment instructions and assess the endpoint's minimum/idle cost before provisioning it.

## Step 4: Verify permissions and diagnostics

Confirm the Vertex AI API is enabled and the runtime identity can invoke the model. Check Cloud Logging and Vertex AI request errors for permission, quota, location, or invalid-model problems. Resolve the actual cause; do not change regions or grant project-wide owner access at random.

## Step 5: Cost and cleanup

Check Vertex AI pricing and quotas before running bulk tests. Managed API calls and deployed prediction endpoints have different pricing models. Do not leave a deployed endpoint running if the model uses provisioned compute.

## Migration work required

The GCP embedding client and mocked unit tests are implemented; the existing AWS ingestion scripts still use SageMaker Runtime. The real Vertex AI model call still needs GCP credentials. Guide 3 adds a separate GCP ingestion/search service, but it requires a provisioned vector index and endpoint before an end-to-end live test. The AWS setup's endpoint name and Terraform outputs are not valid Vertex AI configuration.

## Next

Continue to [3_ingest.md](3_ingest.md) to connect embeddings to Google Cloud storage and vector search.
