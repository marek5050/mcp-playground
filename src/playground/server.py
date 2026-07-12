"""Playground MCP server for mcpbuilders.dev.

Every /mcp request needs a Google-issued token — Claude clients auto-trigger
the OAuth flow on first connect (stock FastMCP enforcement). Set
``AUTH_MODE=off`` for local dataset hacking without OAuth.
"""

from __future__ import annotations

import mcp.types as mcp_types
from fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from playground.config import Settings, load_settings
from playground.middleware import ApiKeyAuthMiddleware, RequireAuthenticatedUser
from playground.tools import campaigns, rag

GOOGLE_OAUTH_SCOPES = ["openid", "email"]

INSTRUCTIONS = """\
Public playground MCP server from mcpbuilders.dev. Two demos in one:

1. MarTech dataset — top_creatives, spend_breakdown, list_campaigns, plus
   per-user save_view / my_views scoped to the caller's Google identity.
2. Hybrid RAG over a public-domain Project Gutenberg corpus (Moby Dick, The
   Adventures of Sherlock Holmes, A Study in Scarlet, The Hound of the
   Baskervilles) — rag_query, list_documents, get_document. Pinecone dense +
   BM25 sparse + RRF + Cohere rerank.
"""


def build_mcp(settings: Settings) -> FastMCP:
    # Auth wired externally in build_app so the API-key path stays independent
    # of the OAuth provider's required_scopes.
    mcp = FastMCP(
        "playground",
        instructions=INSTRUCTIONS,
        auth=None,
        website_url="https://mcpbuilders.dev",
        icons=[
            mcp_types.Icon(
                src="https://mcpbuilders.dev/assets/google-auth-icon-512.png",
                mimeType="image/png",
                sizes=["512x512"],
            )
        ],
    )
    campaigns.register(mcp)
    rag.register(mcp, settings)

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
        required_scopes=GOOGLE_OAUTH_SCOPES,
    )


def build_app(settings: Settings | None = None) -> Starlette:
    settings = settings or load_settings()
    mcp = build_mcp(settings)
    api_key_mw = Middleware(ApiKeyAuthMiddleware, api_key=settings.api_key)

    if settings.auth_mode == "off":
        return mcp.http_app(path="/mcp", middleware=[api_key_mw])

    provider = _google_provider(settings)
    resource_metadata_url = f"{settings.base_url}/.well-known/oauth-protected-resource/mcp"
    middleware: list[Middleware] = [
        *provider.get_middleware(),
        api_key_mw,
        Middleware(RequireAuthenticatedUser, resource_metadata_url=resource_metadata_url),
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
