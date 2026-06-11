"""End-to-end tests of the mixed-mode auth wiring over real HTTP.

Spins up the actual ASGI app (uvicorn in a thread) with a stub Google provider
whose verify_token accepts a known test token, then exercises discovery, DCR,
anonymous access, gated-tool errors, and the authenticated path.
"""

from __future__ import annotations

import socket
import threading
import time

import httpx
import pytest
import uvicorn
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from fastmcp.server.auth.auth import AccessToken
from fastmcp.server.auth.providers.google import GoogleProvider

import playground.server as server_mod
from playground.config import Settings

TEST_TOKEN = "test-valid-token"
TEST_EMAIL = "tester@example.com"


class StubGoogleProvider(GoogleProvider):
    async def verify_token(self, token: str) -> AccessToken | None:
        if token == TEST_TOKEN:
            return AccessToken(
                token=token,
                client_id="user-123",
                scopes=["openid", "https://www.googleapis.com/auth/userinfo.email"],
                expires_at=None,
                claims={"sub": "user-123", "email": TEST_EMAIL},
            )
        return None


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def base_url(monkeypatch_module):
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    settings = Settings(
        base_url=base,
        port=port,
        auth_mode="mixed",
        google_oauth_client_id="dummy.apps.googleusercontent.com",
        google_oauth_client_secret="GOCSPX-dummy",
    )
    monkeypatch_module.setattr(
        server_mod,
        "_google_provider",
        lambda s: StubGoogleProvider(
            client_id=s.google_oauth_client_id,
            client_secret=s.google_oauth_client_secret,
            base_url=s.base_url,
            required_scopes=["openid", "email"],
        ),
    )
    app = server_mod.build_app(settings)
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            if httpx.get(f"{base}/healthz", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.05)
    else:
        pytest.fail("server did not start")
    yield base
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture(scope="module")
def monkeypatch_module():
    mp = pytest.MonkeyPatch()
    yield mp
    mp.undo()


def test_discovery_documents(base_url):
    prm = httpx.get(f"{base_url}/.well-known/oauth-protected-resource/mcp").json()
    assert prm["resource"] == f"{base_url}/mcp"
    assert prm["authorization_servers"]

    asm = httpx.get(f"{base_url}/.well-known/oauth-authorization-server").json()
    assert asm["registration_endpoint"]
    assert "S256" in asm["code_challenge_methods_supported"]
    assert asm["authorization_endpoint"].endswith("/authorize")
    assert asm["token_endpoint"].endswith("/token")


def test_dynamic_client_registration(base_url):
    resp = httpx.post(
        f"{base_url}/register",
        json={"redirect_uris": ["http://localhost:9999/cb"], "client_name": "pytest"},
    )
    assert resp.status_code == 201
    assert resp.json()["client_id"]


def test_invalid_bearer_gets_401_with_www_authenticate(base_url):
    resp = httpx.post(
        f"{base_url}/mcp",
        headers={
            "Authorization": "Bearer bogus",
            "Accept": "application/json, text/event-stream",
        },
        json={"jsonrpc": "2.0", "method": "initialize", "id": 1, "params": {
            "protocolVersion": "2025-06-18", "capabilities": {},
            "clientInfo": {"name": "t", "version": "0"}}},
    )
    assert resp.status_code == 401
    assert "resource_metadata" in resp.headers["www-authenticate"]


async def test_anonymous_can_list_and_call_open_tools(base_url):
    async with Client(f"{base_url}/mcp") as client:
        tools = sorted(t.name for t in await client.list_tools())
        assert tools == [
            "list_campaigns", "my_views", "save_view", "spend_breakdown", "top_creatives",
        ]
        result = await client.call_tool("top_creatives", {"window": "7d", "limit": 3})
        rows = [(c["creative_id"], c["roas"], c["spend"]) for c in result.data["creatives"]]
        assert rows == [
            ("video_demo_v2", 4.8, 12000.0),
            ("carousel_holiday", 3.9, 8000.0),
            ("static_v7", 3.2, 14000.0),
        ]


async def test_anonymous_gated_tool_returns_sign_in_help(base_url):
    async with Client(f"{base_url}/mcp") as client:
        with pytest.raises(Exception, match="Sign-in required"):
            await client.call_tool("my_views", {})


async def test_authenticated_gated_tools_scope_to_user(base_url):
    transport = StreamableHttpTransport(
        f"{base_url}/mcp", headers={"Authorization": f"Bearer {TEST_TOKEN}"}
    )
    async with Client(transport) as client:
        saved = await client.call_tool(
            "save_view", {"name": "winners", "tool": "top_creatives", "params": {"limit": 3}}
        )
        assert saved.data["owner"] == TEST_EMAIL
        views = await client.call_tool("my_views", {})
        assert views.data["owner"] == TEST_EMAIL
        assert "winners" in views.data["views"]
