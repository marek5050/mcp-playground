"""Demo MarTech dataset: load, window filtering, and aggregation helpers."""

from __future__ import annotations

import json
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA_FILE = Path(__file__).parent / "campaigns.json"

WINDOWS = {"7d": 7, "30d": 30, "90d": 90}
DIMENSIONS = ("channel", "campaign", "creative_type")


@lru_cache(maxsize=1)
def _load() -> dict[str, Any]:
    data = json.loads(DATA_FILE.read_text())
    campaigns = {c["id"]: c for c in data["campaigns"]}
    creatives = {c["id"]: c for c in data["creatives"]}
    for c in creatives.values():
        c["channel"] = campaigns[c["campaign_id"]]["channel"]
        c["campaign"] = campaigns[c["campaign_id"]]["name"]
    return {"campaigns": campaigns, "creatives": creatives, "daily": data["daily"]}


def _window_days(window: str) -> int:
    if window not in WINDOWS:
        raise ValueError(f"window must be one of {sorted(WINDOWS)}, got {window!r}")
    return WINDOWS[window]


def _rows(window: str) -> list[dict[str, Any]]:
    days = _window_days(window)
    return [r for r in _load()["daily"] if r["day_offset"] < days]


def _date_range(window: str) -> dict[str, str]:
    days = _window_days(window)
    today = date.today()
    return {"from": str(today - timedelta(days=days - 1)), "to": str(today)}


def _aggregate(rows: list[dict[str, Any]], key_fn) -> dict[str, dict[str, float]]:
    totals: dict[str, dict[str, float]] = {}
    for r in rows:
        bucket = totals.setdefault(key_fn(r), {
            "spend": 0.0, "revenue": 0.0, "impressions": 0, "clicks": 0, "conversions": 0.0,
        })
        for metric in bucket:
            bucket[metric] += r[metric]
    return totals


def _finalize(metrics: dict[str, float]) -> dict[str, Any]:
    spend, revenue = metrics["spend"], metrics["revenue"]
    return {
        "spend": round(spend, 2),
        "revenue": round(revenue, 2),
        "roas": round(revenue / spend, 2) if spend else 0.0,
        "impressions": int(metrics["impressions"]),
        "clicks": int(metrics["clicks"]),
        "conversions": round(metrics["conversions"], 1),
    }


def top_creatives(window: str = "7d", limit: int = 10) -> dict[str, Any]:
    """Creatives ranked by ROAS over the window."""
    creatives = _load()["creatives"]
    totals = _aggregate(_rows(window), lambda r: r["creative_id"])
    ranked = [
        {
            "creative_id": cid,
            "campaign": creatives[cid]["campaign"],
            "channel": creatives[cid]["channel"],
            "creative_type": creatives[cid]["creative_type"],
            **_finalize(metrics),
        }
        for cid, metrics in totals.items()
    ]
    ranked.sort(key=lambda c: c["roas"], reverse=True)
    return {"window": window, **_date_range(window), "creatives": ranked[: max(1, limit)]}


def spend_breakdown(dimension: str = "channel", window: str = "7d") -> dict[str, Any]:
    """Spend/revenue totals grouped by channel, campaign, or creative_type."""
    if dimension not in DIMENSIONS:
        raise ValueError(f"dimension must be one of {DIMENSIONS}, got {dimension!r}")
    creatives = _load()["creatives"]
    totals = _aggregate(_rows(window), lambda r: creatives[r["creative_id"]][dimension])
    total_spend = sum(m["spend"] for m in totals.values()) or 1.0
    groups = [
        {dimension: key, **_finalize(metrics),
         "spend_share": round(metrics["spend"] / total_spend, 3)}
        for key, metrics in totals.items()
    ]
    groups.sort(key=lambda g: g["spend"], reverse=True)
    return {
        "window": window, **_date_range(window), "dimension": dimension,
        "total_spend": round(total_spend, 2), "groups": groups,
    }


def list_campaigns() -> dict[str, Any]:
    """All campaigns with creative counts and 90d totals."""
    data = _load()
    totals = _aggregate(_rows("90d"), lambda r: data["creatives"][r["creative_id"]]["campaign_id"])
    campaigns = [
        {
            "id": c["id"],
            "name": c["name"],
            "channel": c["channel"],
            "objective": c["objective"],
            "status": c["status"],
            "creatives": [k for k, cr in data["creatives"].items() if cr["campaign_id"] == c["id"]],
            **_finalize(totals.get(c["id"], {
                "spend": 0.0, "revenue": 0.0, "impressions": 0, "clicks": 0, "conversions": 0.0,
            })),
        }
        for c in data["campaigns"].values()
    ]
    return {"window": "90d", **_date_range("90d"), "campaigns": campaigns}
