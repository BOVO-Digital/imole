from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse

from app.auth import authorize_request
from app.config import Settings, get_settings
from app.proxy import openai_error, proxy_request


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    app.state.http = httpx.AsyncClient(
        timeout=httpx.Timeout(settings.request_timeout, connect=30.0),
        follow_redirects=True,
        limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
    )
    yield
    await app.state.http.aclose()


app = FastAPI(
    title="Imole OpenAI Gateway",
    description="Proxy OpenAI-compatible vers https://api.imole.app/v1",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health(settings: Settings = Depends(get_settings)) -> dict:
    return {
        "status": "ok",
        "upstream": settings.imole_base_url,
        "auth_required": bool(settings.gateway_api_key.strip()),
    }


@app.get("/")
async def root() -> dict:
    return {
        "name": "Imole OpenAI Gateway",
        "base_url": "/v1",
        "docs": "/docs",
        "health": "/health",
        "compatible": [
            "GET /v1/models",
            "POST /v1/chat/completions",
            "POST /v1/responses",
            "POST /v1/images/generations",
            "POST /v1/images/edits",
            "POST /v1/audio/speech",
            "POST /v1/audio/transcriptions",
            "POST /v1/videos",
        ],
    }


@app.api_route(
    "/v1/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
)
async def openai_compatible(
    path: str,
    request: Request,
    settings: Settings = Depends(get_settings),
    _: None = Depends(authorize_request),
):
    if not settings.imole_api_key.strip():
        return JSONResponse(
            status_code=500,
            content=openai_error(
                "IMOLE_API_KEY is not configured on the gateway.",
                status_code=500,
                code="missing_upstream_key",
            ),
        )

    try:
        return await proxy_request(request, settings, path)
    except httpx.HTTPError as exc:
        return JSONResponse(
            status_code=502,
            content=openai_error(
                f"Upstream request failed: {exc.__class__.__name__}",
                status_code=502,
                code="upstream_error",
            ),
        )
    except RuntimeError as exc:
        return JSONResponse(
            status_code=500,
            content=openai_error(str(exc), status_code=500),
        )
