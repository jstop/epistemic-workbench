"""Remote mode: one bearer token in front of the MCP endpoint and the web API.

Set EPISTEME_TOKEN and the process is "remote": every request to a protected
path must carry `Authorization: Bearer <token>`. Unset, nothing changes and the
servers behave as the local, stdio / loopback tools they always were.

The same middleware guards both processes (the MCP server over streamable HTTP
and the FastAPI web app) so there is exactly one rule for who may write.
"""
from __future__ import annotations

import hmac
import os

PROTECTED_PREFIXES = ("/mcp", "/api")
OPEN_PATHS = ("/healthz",)


def token() -> str | None:
    t = (os.environ.get("EPISTEME_TOKEN") or "").strip()
    return t or None


def remote_mode() -> bool:
    return token() is not None


def valid_workspace_name(name: str) -> bool:
    """In remote mode a workspace is a name, never a path."""
    if not name or len(name) > 64:
        return False
    if name.startswith(("/", ".")) or ".." in name or "\\" in name:
        return False
    return all(c.isalnum() or c in "._-" for c in name)


class BearerAuthMiddleware:
    """Pure ASGI middleware: 401 on protected paths without the right bearer token.
    OPTIONS passes through so CORS preflights still work (they carry no credentials)."""

    def __init__(self, app, protected=PROTECTED_PREFIXES, open_paths=OPEN_PATHS):
        self.app = app
        self.protected = tuple(protected)
        self.open_paths = tuple(open_paths)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        expected = token()
        path = scope.get("path") or "/"
        if expected is None or path in self.open_paths or scope.get("method") == "OPTIONS" \
                or not path.startswith(self.protected):
            return await self.app(scope, receive, send)
        auth = ""
        for k, v in scope.get("headers") or []:
            if k == b"authorization":
                auth = v.decode("latin-1")
                break
        presented = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        if presented and hmac.compare_digest(presented, expected):
            return await self.app(scope, receive, send)
        body = b'{"detail":"unauthorized"}'
        await send({"type": "http.response.start", "status": 401,
                    "headers": [(b"content-type", b"application/json"),
                                (b"content-length", str(len(body)).encode()),
                                (b"www-authenticate", b"Bearer")]})
        await send({"type": "http.response.body", "body": body})


async def healthz(request):
    """Open liveness route for the proxy / load balancer (a Starlette endpoint)."""
    from starlette.responses import JSONResponse
    return JSONResponse({"ok": True})
