#!/bin/zsh
set -euo pipefail

PROJECT_ID="cyber-analyzer-512414"
REGION="asia-south1"
SERVICE="alex-ingestion"
TENANT="alex-guide3-test-$RANDOM"
OTHER_TENANT="${TENANT}-other"
PROXY_PORT="${ALEX_INGESTION_PROXY_PORT:-8765}"
INGEST_URL="http://127.0.0.1:$PROXY_PORT"

gcloud run services proxy "$SERVICE" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --port="$PROXY_PORT" &
PROXY_PID=$!
cleanup() {
  kill "$PROXY_PID" 2>/dev/null || true
  wait "$PROXY_PID" 2>/dev/null || true
}
trap cleanup EXIT

PROXY_READY=0
for attempt in {1..30}; do
  if curl --silent --output /dev/null --connect-timeout 1 \
    --fail "$INGEST_URL/openapi.json" 2>/dev/null; then
    PROXY_READY=1
    break
  fi
  if ! kill -0 "$PROXY_PID" 2>/dev/null; then
    echo "Cloud Run proxy exited before becoming ready." >&2
    exit 1
  fi
  sleep 1
done
if (( ! PROXY_READY )); then
  echo "Cloud Run proxy did not become ready on port $PROXY_PORT." >&2
  exit 1
fi

echo "Checking ingestion API..."
curl --fail-with-body -sS -o /dev/null "$INGEST_URL/openapi.json"
echo "API is responding."
printf '\n'

echo "Ingesting a test document for tenant: $TENANT"
curl --fail-with-body -sS -X POST "$INGEST_URL/ingest" \
  -H "Content-Type: application/json" \
  -d "{\"text\":\"Guide 3 test document: Cloud SQL stores research documents and pgvector embeddings. Test ID: $TENANT\",\"tenant_id\":\"$TENANT\",\"metadata\":{\"source\":\"guide3-smoke-test\"}}"
printf '\n\n'

echo "Searching the same tenant (expect the test document in results)..."
curl --fail-with-body -sS -X POST "$INGEST_URL/search" \
  -H "Content-Type: application/json" \
  -d "{\"query\":\"Where are research documents and pgvector embeddings stored? Test ID: $TENANT\",\"tenant_id\":\"$TENANT\",\"limit\":5}"
printf '\n\n'

echo "Searching another tenant (expect count 0 and no results)..."
curl --fail-with-body -sS -X POST "$INGEST_URL/search" \
  -H "Content-Type: application/json" \
  -d "{\"query\":\"Where are research documents and pgvector embeddings stored?\",\"tenant_id\":\"$OTHER_TENANT\",\"limit\":5}"
printf '\n'