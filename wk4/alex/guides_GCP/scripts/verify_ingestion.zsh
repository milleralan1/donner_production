#!/bin/zsh
set -euo pipefail

PROJECT_ID="cyber-analyzer-511615"
REGION="asia-south1"
SERVICE="alex-ingestion"
TENANT="alex-guide3-test-$RANDOM"
OTHER_TENANT="${TENANT}-other"

INGEST_URL=$(gcloud run services describe "$SERVICE" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --format='value(status.url)')

TOKEN=$(gcloud auth print-identity-token --audiences="$INGEST_URL")
trap 'unset TOKEN' EXIT

echo "Checking health..."
curl --fail-with-body -sS "$INGEST_URL/healthz" \
  -H "Authorization: Bearer $TOKEN"
printf '\n\n'

echo "Ingesting a test document for tenant: $TENANT"
curl --fail-with-body -sS -X POST "$INGEST_URL/ingest" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"text\":\"Guide 3 test document: Cloud SQL stores research documents and pgvector embeddings. Test ID: $TENANT\",\"tenant_id\":\"$TENANT\",\"metadata\":{\"source\":\"guide3-smoke-test\"}}"
printf '\n\n'

echo "Searching the same tenant (expect the test document in results)..."
curl --fail-with-body -sS -X POST "$INGEST_URL/search" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"query\":\"Where are research documents and pgvector embeddings stored? Test ID: $TENANT\",\"tenant_id\":\"$TENANT\",\"limit\":5}"
printf '\n\n'

echo "Searching another tenant (expect count 0 and no results)..."
curl --fail-with-body -sS -X POST "$INGEST_URL/search" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"query\":\"Where are research documents and pgvector embeddings stored?\",\"tenant_id\":\"$OTHER_TENANT\",\"limit\":5}"
printf '\n'