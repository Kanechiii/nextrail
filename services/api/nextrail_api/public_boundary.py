"""Opt-in, fail-closed public HTTPS and origin boundary for a single API host.

No forwarded headers are trusted here. Operators must configure TLS termination
and any ASGI proxy trust rules independently before enabling public exposure.
"""
import re
from urllib.parse import urlsplit

from fastapi.responses import JSONResponse

HOST = re.compile(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}\Z")


class PublicBoundaryError(ValueError):
    """The requested public API origin is unsafe or unsupported."""


def public_host(origin):
    """Accept only a canonical HTTPS DNS origin on the default TLS port."""
    if not isinstance(origin, str) or not 12 <= len(origin) <= 255:
        raise PublicBoundaryError("A canonical HTTPS public origin is required")
    if any(ord(char) <= 32 or ord(char) == 127 for char in origin):
        raise PublicBoundaryError("Public origin contains whitespace or control characters")
    try:
        parts = urlsplit(origin)
        port = parts.port
    except ValueError as exc:
        raise PublicBoundaryError("Invalid public origin") from exc
    host = parts.hostname
    if (parts.scheme != "https" or not host or not HOST.fullmatch(host)
            or parts.username is not None or parts.password is not None
            or port is not None or parts.path or parts.query or parts.fragment
            or parts.netloc != host):
        raise PublicBoundaryError("Public origin must be exactly https://<lowercase-dns-host>")
    return host


async def enforce_public_boundary(request, call_next, *, origin, host):
    """Return generic errors without redirects or proxy-forwarded host trust."""
    peer_host = request.headers.get("host", "").lower()
    if (request.url.scheme != "https"
            or peer_host not in (host, host + ":443")
            or (request.headers.get("origin") is not None
                and request.headers["origin"] != origin)):
        return JSONResponse(
            status_code=403,
            content={"detail": "Public request boundary rejected"},
        )
    response = await call_next(request)
    response.headers["Strict-Transport-Security"] = "max-age=31536000"
    return response
