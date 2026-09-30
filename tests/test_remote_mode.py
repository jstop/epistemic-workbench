"""Remote mode (EPISTEME_TOKEN set): one bearer token guards /mcp and /api, and a
workspace is a name, never a path. Unset, nothing here applies."""
import importlib
import os

import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from epist import auth


def _app():
    async def echo(request):
        return JSONResponse({"path": request.url.path})
    a = Starlette(routes=[Route("/healthz", auth.healthz), Route("/api/x", echo, methods=["GET", "POST", "OPTIONS"]),
                          Route("/mcp", echo, methods=["POST"]), Route("/", echo)])
    a.add_middleware(auth.BearerAuthMiddleware)
    return TestClient(a)


def test_without_token_everything_is_open(monkeypatch):
    monkeypatch.delenv("EPISTEME_TOKEN", raising=False)
    c = _app()
    assert c.get("/api/x").status_code == 200
    assert c.post("/mcp").status_code == 200
    assert not auth.remote_mode()


def test_with_token_protected_paths_need_it(monkeypatch):
    monkeypatch.setenv("EPISTEME_TOKEN", "s3cret")
    c = _app()
    assert auth.remote_mode()
    assert c.get("/api/x").status_code == 401
    assert c.post("/mcp").status_code == 401
    assert c.get("/api/x", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert c.get("/api/x", headers={"Authorization": "Bearer s3cret"}).status_code == 200
    assert c.post("/mcp", headers={"Authorization": "Bearer s3cret"}).status_code == 200
    # the open bits stay open: liveness, the SPA, and CORS preflights
    assert c.get("/healthz").status_code == 200
    assert c.get("/").status_code == 200
    assert c.options("/api/x").status_code == 200


@pytest.mark.parametrize("name,ok", [
    ("expertise-vs-authority", True), ("a.b_c-1", True),
    ("../etc", False), ("/tmp/x", False), (".hidden", False), ("a/b", False), ("", False), ("x" * 65, False),
])
def test_workspace_names_are_names(name, ok):
    assert auth.valid_workspace_name(name) is ok


def test_mcp_server_rejects_paths_only_in_remote_mode(monkeypatch, tmp_path):
    from epist import mcp_server
    monkeypatch.delenv("EPISTEME_TOKEN", raising=False)
    assert mcp_server._resolve_workspace(str(tmp_path)) == tmp_path          # local: paths allowed
    monkeypatch.setenv("EPISTEME_TOKEN", "s3cret")
    with pytest.raises(ValueError):
        mcp_server._resolve_workspace(str(tmp_path))
    assert mcp_server._resolve_workspace("demo") == mcp_server.WORKSPACES_DIR / "demo"
