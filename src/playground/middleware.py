"""Optional-auth middleware for AUTH_MODE=mixed.

The auth provider's standard middleware (AuthenticationMiddleware +
AuthContextMiddleware) verifies a Bearer token when one is presented but never
rejects anonymous requests. This middleware adds the one missing piece: if a
client DID present a token and it failed verification, answer 401 with a
WWW-Authenticate header pointing at the protected-resource metadata, so MCP
clients know to refresh or re-run the OAuth flow. Requests without an
Authorization header pass through anonymously.
"""

from __future__ import annotations

from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send


class OptionalAuthMiddleware:
    def __init__(self, app: ASGIApp, resource_metadata_url: str, mcp_path: str = "/mcp"):
        self.app = app
        self.resource_metadata_url = resource_metadata_url
        self.mcp_path = mcp_path.rstrip("/")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope["path"].rstrip("/").startswith(self.mcp_path):
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        has_bearer = request.headers.get("authorization", "").lower().startswith("bearer ")
        if has_bearer and not isinstance(scope.get("user"), AuthenticatedUser):
            response = JSONResponse(
                {"error": "invalid_token", "error_description": "Bearer token is invalid or expired"},
                status_code=401,
                headers={
                    "WWW-Authenticate": (
                        f'Bearer error="invalid_token", '
                        f'resource_metadata="{self.resource_metadata_url}"'
                    )
                },
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
