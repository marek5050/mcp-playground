"""Auth middlewares for the playground server.

Two pieces:

- ``ApiKeyAuthMiddleware`` accepts ``Authorization: Bearer <api_key>`` as a
  self-contained authenticated user, independent of any OAuth provider.
- ``RequireAuthenticatedUser`` enforces that every ``/mcp`` request carries an
  ``AuthenticatedUser`` (either OAuth or API key), answering 401 with the
  protected-resource metadata pointer otherwise. Replaces the MCP SDK's
  built-in ``RequireAuthMiddleware`` because that one enforces the OAuth
  provider's ``required_scopes``, which the API-key path has no business
  carrying.
"""

from __future__ import annotations

from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from mcp.server.auth.provider import AccessToken
from starlette.authentication import AuthCredentials
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send


API_KEY_CLIENT_ID = "api-key"
API_KEY_SUBJECT = "api-key-user"


class ApiKeyAuthMiddleware:
    def __init__(self, app: ASGIApp, api_key: str):
        self.app = app
        self.api_key = api_key

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and self.api_key and not isinstance(
            scope.get("user"), AuthenticatedUser
        ):
            header = Request(scope).headers.get("authorization", "")
            if header.lower().startswith("bearer "):
                token = header.split(" ", 1)[1].strip()
                if token == self.api_key:
                    access_token = AccessToken(
                        token=token,
                        client_id=API_KEY_CLIENT_ID,
                        scopes=[],
                        subject=API_KEY_SUBJECT,
                        claims={"sub": API_KEY_SUBJECT, "email": "api-key@playground"},
                    )
                    scope["user"] = AuthenticatedUser(access_token)
                    scope["auth"] = AuthCredentials(scopes=[])
        await self.app(scope, receive, send)


class RequireAuthenticatedUser:
    def __init__(self, app: ASGIApp, resource_metadata_url: str, mcp_path: str = "/mcp"):
        self.app = app
        self.resource_metadata_url = resource_metadata_url
        self.mcp_path = mcp_path.rstrip("/")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope["path"].rstrip("/").startswith(self.mcp_path):
            await self.app(scope, receive, send)
            return
        if isinstance(scope.get("user"), AuthenticatedUser):
            await self.app(scope, receive, send)
            return
        response = JSONResponse(
            {"error": "invalid_token", "error_description": "Authentication required"},
            status_code=401,
            headers={
                "WWW-Authenticate": (
                    f'Bearer error="invalid_token", '
                    f'resource_metadata="{self.resource_metadata_url}"'
                )
            },
        )
        await response(scope, receive, send)