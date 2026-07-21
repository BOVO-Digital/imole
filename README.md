# Imole OpenAI Gateway

Proxy **compatible OpenAI** devant [`https://api.imole.app/v1`](https://api.imole.app/v1).

## Production

| | |
|---|---|
| URL | https://imole.bovo-digital.tech |
| Base URL OpenAI | `https://imole.bovo-digital.tech/v1` |
| Auth client | `Authorization: Bearer <GATEWAY_API_KEY>` |

Stack VPS : Docker + Traefik (`n8n_default`), même pattern que [bovo-core](https://github.com/BOVO-Digital/bovo-core).

```bash
# Sur le VPS
cd /opt/imole
docker compose -f docker-compose.vps.yml up -d
```

## Local

```bash
cp .env.example .env
docker compose up -d --build
# http://127.0.0.1:3275/v1
```

## CI/CD

Push sur `main` → build image `ghcr.io/bovo-digital/imole` → deploy `/opt/imole` sur le VPS.

Secrets GitHub requis : `VPS_HOST`, `VPS_USER`, `VPS_SSH_KEY`, `IMOLE_API_KEY`, `GATEWAY_API_KEY`.
