#!/usr/bin/env bash
# Crée (ou réutilise) un tunnel Cloudflare nommé avec hostname FIXE.
# Prérequis : cloudflared installé + compte Cloudflare authentifié.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  echo "Créez d'abord .env depuis .env.example"
  exit 1
fi

# shellcheck disable=SC1091
set -a
source .env
set +a

: "${CF_TUNNEL_NAME:?CF_TUNNEL_NAME manquant dans .env}"
: "${CF_HOSTNAME:?CF_HOSTNAME manquant dans .env}"

mkdir -p cloudflare/credentials

echo "==> Authentification Cloudflare (ouvre le navigateur si besoin)"
cloudflared tunnel login || true

echo "==> Création / récupération du tunnel nommé: ${CF_TUNNEL_NAME}"
if ! cloudflared tunnel list 2>/dev/null | grep -q "${CF_TUNNEL_NAME}"; then
  cloudflared tunnel create "${CF_TUNNEL_NAME}"
else
  echo "Tunnel déjà existant — réutilisation (hostname stable)."
fi

TUNNEL_ID="$(cloudflared tunnel list | awk -v n="${CF_TUNNEL_NAME}" '$2==n {print $1; exit}')"
if [[ -z "${TUNNEL_ID}" ]]; then
  echo "Impossible de résoudre l'ID du tunnel ${CF_TUNNEL_NAME}"
  exit 1
fi

CREDS_SRC="${HOME}/.cloudflared/${TUNNEL_ID}.json"
CREDS_DST="cloudflare/credentials/${TUNNEL_ID}.json"
if [[ -f "${CREDS_SRC}" ]]; then
  cp "${CREDS_SRC}" "${CREDS_DST}"
  chmod 600 "${CREDS_DST}"
else
  echo "Credentials introuvables: ${CREDS_SRC}"
  exit 1
fi

echo "==> Écriture cloudflare/config.yml (hostname fixe: ${CF_HOSTNAME})"
sed \
  -e "s/TUNNEL_ID/${TUNNEL_ID}/g" \
  -e "s/CF_HOSTNAME/${CF_HOSTNAME}/g" \
  cloudflare/config.template.yml > cloudflare/config.yml

echo "==> DNS CNAME ${CF_HOSTNAME} → ${TUNNEL_ID}.cfargotunnel.com"
cloudflared tunnel route dns "${CF_TUNNEL_NAME}" "${CF_HOSTNAME}"

echo
echo "OK. Hostname stable: https://${CF_HOSTNAME}/v1"
echo "Base URL OpenAI:     https://${CF_HOSTNAME}/v1"
echo
echo "Démarrer avec:"
echo "  docker compose --profile tunnel-file up -d --build"
echo
echo "Ou via token Zero Trust (dashboard Cloudflare → Tunnel → Install):"
echo "  mettez CF_TUNNEL_TOKEN dans .env puis:"
echo "  docker compose --profile tunnel up -d --build"
