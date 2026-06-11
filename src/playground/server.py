"""Playground MCP server for mcpbuilders.dev.

Anonymous read-only MarTech demo tools, plus per-user tools behind Google
sign-in (OAuth client from the mcp-builders GCP project). AUTH_MODE controls
the wiring:

- mixed (default): anonymous tools work without a token; gated tools require
  one. OAuth endpoints are mounted so Claude clients can authenticate.
- required: every /mcp request needs a token — Claude auto-triggers the OAuth
  flow on first connect (stock FastMCP enforcement).
- off: no auth wiring at all (local dataset hacking).
"""

from __future__ import annotations

from fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from playground.config import Settings, load_settings
from playground.middleware import OptionalAuthMiddleware
from playground.tools import campaigns, gated

INSTRUCTIONS = """\
Public playground MCP server from mcpbuilders.dev. Read-only demo MarTech
dataset (campaigns, creatives, daily spend). top_creatives, spend_breakdown,
and list_campaigns work anonymously. save_view and my_views demonstrate
per-user OAuth: they require Google sign-in and scope data to your identity.
"""


def build_mcp(settings: Settings) -> FastMCP:
    auth = None
    if settings.auth_mode == "required":
        auth = _google_provider(settings)
    mcp = FastMCP("playground", instructions=INSTRUCTIONS, auth=auth)
    campaigns.register(mcp)
    gated.register(mcp)

    @mcp.custom_route("/healthz", methods=["GET"], include_in_schema=False)
    async def healthz(_: Request) -> JSONResponse:
        return JSONResponse({"status": "ok", "auth_mode": settings.auth_mode})

    return mcp


def _google_provider(settings: Settings):
    from fastmcp.server.auth.providers.google import GoogleProvider

    return GoogleProvider(
        client_id=settings.google_oauth_client_id,
        client_secret=settings.google_oauth_client_secret,
        base_url=settings.base_url,
        required_scopes=["openid", "email"],
    )


def build_app(settings: Settings | None = None) -> Starlette:
    settings = settings or load_settings()
    mcp = build_mcp(settings)

    if settings.auth_mode != "mixed":
        # off: plain app; required: FastMCP wires enforcement + OAuth routes itself
        return mcp.http_app(path="/mcp")

    # mixed: token verification WITHOUT enforcement. The provider's middleware
    # populates the auth context when a Bearer token is present but never
    # rejects anonymous requests (rejection lives in RequireAuthMiddleware,
    # which only FastMCP(auth=...) installs).
    provider = _google_provider(settings)
    resource_metadata_url = f"{settings.base_url}/.well-known/oauth-protected-resource/mcp"
    middleware = [
        *provider.get_middleware(),
        Middleware(OptionalAuthMiddleware, resource_metadata_url=resource_metadata_url),
    ]
    app = mcp.http_app(path="/mcp", middleware=middleware)
    # discovery docs + /register + /authorize + /token + /auth/callback
    app.router.routes.extend(provider.get_routes(mcp_path="/mcp"))
    return app


def main() -> None:
    import uvicorn

    settings = load_settings()
    uvicorn.run(build_app(settings), host="0.0.0.0", port=settings.port)


if __name__ == "__main__":
    main()
