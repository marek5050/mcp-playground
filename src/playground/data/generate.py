"""One-off generator for campaigns.json.

Produces 90 days of daily performance rows keyed by day_offset (0 = today),
constructed so the last-7-days totals reproduce the numbers advertised on
mcpbuilders.dev exactly:

    1. video_demo_v2    — ROAS 4.8, $12k spend
    2. carousel_holiday — ROAS 3.9, $8k  spend
    3. static_v7        — ROAS 3.2, $14k spend

Run: python -m playground.data.generate
"""

from __future__ import annotations

import json
import math
from pathlib import Path

OUT = Path(__file__).parent / "campaigns.json"

CAMPAIGNS = [
    {"id": "cmp_demo_launch", "name": "Product Demo Launch", "channel": "meta", "objective": "conversions", "status": "active"},
    {"id": "cmp_holiday", "name": "Holiday Promo", "channel": "google", "objective": "sales", "status": "active"},
    {"id": "cmp_evergreen", "name": "Evergreen Retargeting", "channel": "meta", "objective": "conversions", "status": "active"},
    {"id": "cmp_prospecting", "name": "Prospecting Broad", "channel": "tiktok", "objective": "traffic", "status": "active"},
    {"id": "cmp_branded_search", "name": "Branded Search", "channel": "bing", "objective": "sales", "status": "active"},
]

# id, campaign_id, creative_type, 7d spend target, 7d ROAS target, cpm, ctr, aov
CREATIVES = [
    ("video_demo_v2", "cmp_demo_launch", "video", 12_000.0, 4.8, 9.0, 0.021, 96.0),
    ("video_demo_v1", "cmp_demo_launch", "video", 5_000.0, 2.6, 9.5, 0.016, 92.0),
    ("carousel_holiday", "cmp_holiday", "carousel", 8_000.0, 3.9, 11.0, 0.024, 78.0),
    ("static_holiday_v1", "cmp_holiday", "static", 4_500.0, 2.9, 10.5, 0.014, 75.0),
    ("static_v7", "cmp_evergreen", "static", 14_000.0, 3.2, 7.5, 0.012, 84.0),
    ("static_v6", "cmp_evergreen", "static", 6_000.0, 2.4, 7.8, 0.010, 81.0),
    ("video_hook_a", "cmp_prospecting", "video", 9_000.0, 1.8, 6.0, 0.018, 64.0),
    ("rsa_brand_core", "cmp_branded_search", "text", 3_000.0, 3.05, 14.0, 0.045, 88.0),
]

# Fixed intra-week distribution; sums to 1 so weekly targets are exact.
DAY_WEIGHTS = [0.12, 0.13, 0.14, 0.15, 0.16, 0.15, 0.15]


def split_week(total: float, base_offset: int) -> dict[int, float]:
    """Split a weekly total across 7 day_offsets, exact to the cent."""
    days = {base_offset + i: round(total * w, 2) for i, w in enumerate(DAY_WEIGHTS)}
    days[base_offset] = round(days[base_offset] + round(total - sum(days.values()), 2), 2)
    return days


def main() -> None:
    daily = []
    for idx, (cid, _camp, _ctype, spend_7d, roas_7d, cpm, ctr, aov) in enumerate(CREATIVES):
        for week in range(13):  # weeks of 7 days -> offsets 0..90; trimmed to <90 below
            if week == 0:
                w_spend, w_roas = spend_7d, roas_7d
            else:
                # deterministic organic-looking drift for historical weeks
                w_spend = spend_7d * (1 + 0.18 * math.sin(week * 1.7 + idx))
                w_roas = roas_7d * (1 + 0.10 * math.sin(week * 1.1 + idx * 2.3))
            spend_days = split_week(w_spend, week * 7)
            revenue_days = split_week(w_spend * w_roas, week * 7)
            for off, spend in spend_days.items():
                if off >= 90:
                    continue
                revenue = revenue_days[off]
                impressions = int(spend / cpm * 1000)
                clicks = int(impressions * ctr)
                conversions = round(revenue / aov, 1)
                daily.append({
                    "creative_id": cid,
                    "day_offset": off,
                    "spend": spend,
                    "revenue": revenue,
                    "impressions": impressions,
                    "clicks": clicks,
                    "conversions": conversions,
                })

    creatives = [
        {"id": cid, "campaign_id": camp, "creative_type": ctype}
        for cid, camp, ctype, *_ in CREATIVES
    ]
    OUT.write_text(json.dumps(
        {"campaigns": CAMPAIGNS, "creatives": creatives, "daily": daily}, indent=1
    ) + "\n")
    print(f"wrote {OUT} ({len(daily)} daily rows)")


if __name__ == "__main__":
    main()
