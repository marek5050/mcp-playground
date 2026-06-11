"""Per-user tools that require Google sign-in.

These deliberately do NOT use ``@mcp.tool(auth=...)`` — that would hide them
from anonymous ``tools/list``. Instead they stay discoverable and return a
sign-in instruction when called without a token.
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_access_token

SIGN_IN_HELP = (
    "Sign-in required. This tool demonstrates per-user OAuth: results are scoped "
    "to YOUR Google identity. In Claude Code run /mcp, select this server, choose "
    "Authenticate, and sign in with Google. In Claude Desktop, open Settings > "
    "Connectors and connect this server. Anonymous tools you can use right now: "
    "top_creatives, spend_breakdown, list_campaigns."
)

# uid -> {view_name: view}; in-memory by design (playground), wiped on restart
VIEWS: dict[str, dict[str, dict[str, Any]]] = {}


def _current_user() -> tuple[str, str]:
    """Return (uid, email) for the caller, or raise with sign-in instructions."""
    token = get_access_token()
    if token is None:
        raise ToolError(SIGN_IN_HELP)
    claims = token.claims or {}
    upstream = claims.get("upstream_claims") or {}
    uid = claims.get("sub") or upstream.get("sub") or token.client_id
    email = claims.get("email") or upstream.get("email") or "unknown"
    return str(uid), str(email)


def register(mcp: FastMCP) -> None:
    @mcp.tool
    def save_view(name: str, tool: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Save a named view (a tool + params you want to re-run later).

        Requires Google sign-in — views are stored per-user, demonstrating
        per-user OAuth and row-level scoping.
        """
        uid, email = _current_user()
        VIEWS.setdefault(uid, {})[name] = {"tool": tool, "params": params or {}}
        return {
            "saved": name,
            "owner": email,
            "total_views": len(VIEWS[uid]),
            "note": "Stored in-memory per-user; this playground forgets on restart.",
        }

    @mcp.tool
    def my_views() -> dict[str, Any]:
        """List the views YOU saved — only ever returns the caller's own data.

        Requires Google sign-in.
        """
        uid, email = _current_user()
        return {"owner": email, "views": VIEWS.get(uid, {})}
