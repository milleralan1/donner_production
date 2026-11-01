#!/bin/zsh
set -euo pipefail

PROJECT_ID="${GOOGLE_CLOUD_PROJECT:-cyber-analyzer-512414}"
REGION="${GOOGLE_CLOUD_REGION:-asia-south1}"
RESEARCHER_SERVICE="alex-researcher"
INGESTION_SERVICE="alex-ingestion"
RESEARCHER_PORT="${ALEX_RESEARCHER_PROXY_PORT:-8080}"
INGESTION_PORT="${ALEX_INGESTION_PROXY_PORT:-8765}"
TENANT_ID="${RESEARCH_TENANT_ID:-public_research}"
TOPIC="${ALEX_RESEARCH_TOPIC:-Compare recent expense ratios and investment risks of two major short-term US Treasury ETFs. Cite sources.}"
REQUEST_TIMEOUT="${ALEX_RESEARCH_TIMEOUT_SECONDS:-900}"
RESEARCHER_URL="http://127.0.0.1:$RESEARCHER_PORT"
INGESTION_URL="http://127.0.0.1:$INGESTION_PORT"
RESEARCH_RESPONSE_FILE=$(mktemp)
SEARCH_RESPONSE_FILE=$(mktemp)
typeset -a PROXY_PIDS

cleanup() {
  for pid in "${PROXY_PIDS[@]}"; do
    kill "$pid" 2>/dev/null || true
    wait "$pid" 2>/dev/null || true
  done
  rm -f "$RESEARCH_RESPONSE_FILE" "$SEARCH_RESPONSE_FILE"
}
trap cleanup EXIT

start_proxy() {
  local service="$1"
  local port="$2"
  local probe_url="$3"
  local pid

  gcloud run services proxy "$service" \
    --project="$PROJECT_ID" \
    --region="$REGION" \
    --port="$port" &
  pid=$!
  PROXY_PIDS+=("$pid")

  for attempt in {1..30}; do
    if curl --silent --output /dev/null --connect-timeout 1 --max-time 3 \
      --fail "$probe_url" 2>/dev/null; then
      return
    fi
    if ! kill -0 "$pid" 2>/dev/null; then
      echo "Cloud Run proxy for $service exited before becoming ready." >&2
      return 1
    fi
    sleep 1
  done

  echo "Cloud Run proxy for $service did not become ready on port $port." >&2
  return 1
}

echo "Starting authenticated proxy for $RESEARCHER_SERVICE..."
start_proxy "$RESEARCHER_SERVICE" "$RESEARCHER_PORT" \
  "$RESEARCHER_URL/openapi.json"
echo "Starting authenticated proxy for $INGESTION_SERVICE..."
start_proxy "$INGESTION_SERVICE" "$INGESTION_PORT" \
  "$INGESTION_URL/openapi.json"

echo "Both APIs are responding. Requesting research on: $TOPIC"
RESEARCH_REQUEST=$(TOPIC="$TOPIC" python3 -c \
  'import json, os; print(json.dumps({"topic": os.environ["TOPIC"]}))')
if ! curl --silent --show-error --fail-with-body \
  --max-time "$REQUEST_TIMEOUT" \
  -X POST "$RESEARCHER_URL/research" \
  -H "Content-Type: application/json" \
  -d "$RESEARCH_REQUEST" \
  --output "$RESEARCH_RESPONSE_FILE"; then
  cat "$RESEARCH_RESPONSE_FILE" >&2
  exit 1
fi

python3 - "$RESEARCH_RESPONSE_FILE" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as response_file:
    payload = json.load(response_file)
research = payload.get("research")
if not isinstance(research, str) or not research.strip():
    raise SystemExit("Researcher response did not contain non-empty research.")
print("\nResearch response:")
print(research)
PY

printf "\nSearching tenant '%s' for the research...\n" "$TENANT_ID"
SEARCH_REQUEST=$(TOPIC="$TOPIC" TENANT_ID="$TENANT_ID" python3 -c \
  'import json, os; print(json.dumps({"query": os.environ["TOPIC"], "tenant_id": os.environ["TENANT_ID"], "limit": 5}))')
if ! curl --silent --show-error --fail-with-body \
  -X POST "$INGESTION_URL/search" \
  -H "Content-Type: application/json" \
  -d "$SEARCH_REQUEST" \
  --output "$SEARCH_RESPONSE_FILE"; then
  cat "$SEARCH_RESPONSE_FILE" >&2
  exit 1
fi

python3 - "$SEARCH_RESPONSE_FILE" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as response_file:
    payload = json.load(response_file)
results = payload.get("results")
if not isinstance(results, list) or not results:
    raise SystemExit("Search returned no results for the research topic.")
print(json.dumps(payload, indent=2))
PY

printf "\nResearcher end-to-end verification succeeded.\n"
