import json
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import urljoin

import httpx
from fastapi import Request, Response
from fastapi.responses import StreamingResponse

from app.config import Settings
from app.sanitize import sanitize_payload

HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
    # httpx décompresse le body → ne jamais retransmettre ces headers tels quels
    "content-encoding",
    "content-length",
}


def upstream_url(settings: Settings, path: str, query: str) -> str:
    base = settings.imole_base_url.rstrip("/") + "/"
    target = urljoin(base, path.lstrip("/"))
    if query:
        target = f"{target}?{query}"
    return target


def build_upstream_headers(request: Request, settings: Settings) -> dict[str, str]:
    headers: dict[str, str] = {}
    for key, value in request.headers.items():
        lower = key.lower()
        if lower in HOP_BY_HOP or lower == "authorization":
            continue
        headers[key] = value

    if not settings.imole_api_key:
        raise RuntimeError("IMOLE_API_KEY is not configured")

    headers["Authorization"] = f"Bearer {settings.imole_api_key}"
    headers.setdefault("Accept", request.headers.get("accept", "*/*"))
    return headers


def _wants_stream(request: Request, body: bytes) -> bool:
    accept = request.headers.get("accept", "")
    if "text/event-stream" in accept:
        return True
    if not body:
        return False
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return False
    return bool(isinstance(payload, dict) and payload.get("stream") is True)


def _rewrite_body(body: bytes) -> bytes:
    """Normalise tools Cursor → schéma attendu par gpt-5.6-* / Imọlẹ."""
    if not body:
        return body
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return body
    if not isinstance(payload, dict):
        return body
    # Toujours normaliser si tools / historique messages (IDs Cursor trop longs, etc.)
    if not any(k in payload for k in ("tools", "tool_choice", "messages", "input")):
        return body
    return json.dumps(sanitize_payload(payload), ensure_ascii=False).encode("utf-8")


async def proxy_request(
    request: Request,
    settings: Settings,
    path: str,
) -> Response:
    url = upstream_url(settings, path, request.url.query)
    headers = build_upstream_headers(request, settings)
    body = _rewrite_body(await request.body())
    client: httpx.AsyncClient = request.app.state.http

    # Content-Length recalculé par httpx ; retirer l'ancien si présent
    headers.pop("Content-Length", None)
    headers.pop("content-length", None)

    if _wants_stream(request, body):
        return await _stream_upstream(
            client, request.method, url, headers, body, settings
        )

    timeout = httpx.Timeout(
        connect=30.0,
        read=settings.request_timeout,
        write=settings.request_timeout,
        pool=30.0,
    )
    upstream = await client.request(
        method=request.method,
        url=url,
        headers=headers,
        content=body if body else None,
        timeout=timeout,
    )
    return _to_response(upstream)


async def _stream_upstream(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    headers: dict[str, str],
    body: bytes,
    settings: Settings,
) -> StreamingResponse:
    # read=None : Cursor agent peut rester silencieux longtemps entre chunks
    timeout = httpx.Timeout(
        connect=30.0,
        read=None,
        write=settings.request_timeout,
        pool=30.0,
    )
    req = client.build_request(
        method=method,
        url=url,
        headers=headers,
        content=body if body else None,
        timeout=timeout,
    )
    upstream = await client.send(req, stream=True)

    async def iterator() -> AsyncIterator[bytes]:
        try:
            # aiter_bytes = body décompressé (aligné avec strip content-encoding)
            async for chunk in upstream.aiter_bytes():
                yield chunk
        finally:
            await upstream.aclose()

    response_headers = _filtered_headers(upstream)
    # Empêche buffering reverse-proxy / CDN sur le SSE
    response_headers["Cache-Control"] = "no-cache, no-transform"
    response_headers["X-Accel-Buffering"] = "no"
    response_headers["Connection"] = "keep-alive"

    return StreamingResponse(
        iterator(),
        status_code=upstream.status_code,
        headers=response_headers,
        media_type=upstream.headers.get("content-type") or "text/event-stream",
    )


def _filtered_headers(upstream: httpx.Response) -> dict[str, str]:
    return {
        k: v
        for k, v in upstream.headers.items()
        if k.lower() not in HOP_BY_HOP
    }


def _to_response(upstream: httpx.Response) -> Response:
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=_filtered_headers(upstream),
        media_type=upstream.headers.get("content-type"),
    )


def openai_error(
    message: str, status_code: int = 500, code: str | None = None
) -> dict[str, Any]:
    return {
        "error": {
            "message": message,
            "type": "server_error" if status_code >= 500 else "invalid_request_error",
            "param": None,
            "code": code,
        }
    }
