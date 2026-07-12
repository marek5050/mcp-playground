"""Campaigns dataset tools + per-user saved views.

Every tool here runs under `AUTH_MODE=required` in production, so callers
always have a verified identity. The `save_view` / `my_views` pair uses that
identity to scope stored state to the caller — the point of the per-user
OAuth demo.
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_access_token

from playground.data import dataset

# uid -> {view_name: view}; in-memory by design (playground), wiped on restart
VIEWS: dict[str, dict[str, dict[str, Any]]] = {}


def _current_user() -> tuple[str, str]:
    token = get_access_token()
    if token is None:
        raise ToolError("Authentication required — sign in with Google to use this tool.")
    claims = token.claims or {}
    upstream = claims.get("upstream_claims") or {}
    uid = claims.get("sub") or upstream.get("sub") or token.client_id
    email = claims.get("email") or upstream.get("email") or "unknown"
    return str(uid), str(email)


def register(mcp: FastMCP) -> None:
    @mcp.tool
    def top_creatives(window: str = "7d", limit: int = 10) -> dict[str, Any]:
        """Top creatives ranked by ROAS over a window (7d, 30d, or 90d)."""
        try:
            return dataset.top_creatives(window=window, limit=limit)
        except ValueError as exc:
            raise ToolError(str(exc)) from exc

    @mcp.tool
    def spend_breakdown(dimension: str = "channel", window: str = "7d") -> dict[str, Any]:
        """Spend and revenue totals grouped by channel, campaign, or creative_type."""
        try:
            return dataset.spend_breakdown(dimension=dimension, window=window)
        except ValueError as exc:
            raise ToolError(str(exc)) from exc

    @mcp.tool
    def list_campaigns() -> dict[str, Any]:
        """All demo campaigns with their creatives and 90-day totals."""
        return dataset.list_campaigns()

    @mcp.tool
    def save_view(name: str, tool: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Save a named view (a tool + params you want to re-run later), scoped to your identity."""
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
        """List the views YOU saved — only ever returns the caller's own data."""
        uid, email = _current_user()
        return {"owner": email, "views": VIEWS.get(uid, {})}