#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# shellcheck disable=SC1091
set -a
source .env
set +a

BASE="${1:-http://127.0.0.1:${PORT:-3275}}"
KEY="${GATEWAY_API_KEY:-}"

AUTH_HEADER=()
if [[ -n "${KEY}" ]]; then
  AUTH_HEADER=(-H "Authorization: Bearer ${KEY}")
fi

echo "==> Health ${BASE}/health"
curl -fsS "${BASE}/health" | python3 -m json.tool

echo
echo "==> Models ${BASE}/v1/models"
curl -fsS "${BASE}/v1/models" "${AUTH_HEADER[@]}" | python3 -m json.tool | head -80

echo
echo "OK"
