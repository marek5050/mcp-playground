"""Anonymous read-only tools over the demo MarTech dataset."""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from playground.data import dataset


def register(mcp: FastMCP) -> None:
    @mcp.tool
    def top_creatives(window: str = "7d", limit: int = 10) -> dict[str, Any]:
        """Top creatives ranked by ROAS over a window (7d, 30d, or 90d).

        Open demo data — no sign-in needed.
        """
        try:
            return dataset.top_creatives(window=window, limit=limit)
        except ValueError as exc:
            raise ToolError(str(exc)) from exc

    @mcp.tool
    def spend_breakdown(dimension: str = "channel", window: str = "7d") -> dict[str, Any]:
        """Spend and revenue totals grouped by channel, campaign, or creative_type.

        Open demo data — no sign-in needed.
        """
        try:
            return dataset.spend_breakdown(dimension=dimension, window=window)
        except ValueError as exc:
            raise ToolError(str(exc)) from exc

    @mcp.tool
    def list_campaigns() -> dict[str, Any]:
        """All demo campaigns with their creatives and 90-day totals.

        Open demo data — no sign-in needed.
        """
        return dataset.list_campaigns()
