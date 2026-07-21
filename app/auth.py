from fastapi import Depends, Header, HTTPException, status

from app.config import Settings, get_settings


def extract_bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def authorize_request(
    settings: Settings = Depends(get_settings),
    authorization: str | None = Header(default=None),
) -> None:
    """Si GATEWAY_API_KEY est défini, le client doit présenter cette clé."""
    expected = settings.gateway_api_key.strip()
    if not expected:
        return

    token = extract_bearer(authorization)
    if token != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "message": "Invalid API key provided.",
                    "type": "invalid_request_error",
                    "param": None,
                    "code": "invalid_api_key",
                }
            },
        )
