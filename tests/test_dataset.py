import pytest

from playground.data import dataset


def test_top_creatives_matches_site_demo():
    """The 7d window must reproduce the rows advertised on mcpbuilders.dev."""
    result = dataset.top_creatives(window="7d", limit=3)
    rows = [(c["creative_id"], c["roas"], c["spend"]) for c in result["creatives"]]
    assert rows == [
        ("video_demo_v2", 4.8, 12000.0),
        ("carousel_holiday", 3.9, 8000.0),
        ("static_v7", 3.2, 14000.0),
    ]


def test_top_creatives_windows_and_limit():
    assert len(dataset.top_creatives(limit=2)["creatives"]) == 2
    for window in ("7d", "30d", "90d"):
        result = dataset.top_creatives(window=window)
        assert result["window"] == window
        assert len(result["creatives"]) == 8
        roas = [c["roas"] for c in result["creatives"]]
        assert roas == sorted(roas, reverse=True)


def test_top_creatives_rejects_bad_window():
    with pytest.raises(ValueError, match="window"):
        dataset.top_creatives(window="1y")


def test_spend_breakdown_shares_sum_to_one():
    for dimension in dataset.DIMENSIONS:
        result = dataset.spend_breakdown(dimension=dimension, window="30d")
        assert result["dimension"] == dimension
        assert sum(g["spend_share"] for g in result["groups"]) == pytest.approx(1.0, abs=0.01)
        assert sum(g["spend"] for g in result["groups"]) == pytest.approx(result["total_spend"])


def test_spend_breakdown_rejects_bad_dimension():
    with pytest.raises(ValueError, match="dimension"):
        dataset.spend_breakdown(dimension="country")


def test_list_campaigns():
    result = dataset.list_campaigns()
    campaigns = {c["id"]: c for c in result["campaigns"]}
    assert len(campaigns) == 5
    assert campaigns["cmp_demo_launch"]["creatives"] == ["video_demo_v2", "video_demo_v1"]
    assert all(c["spend"] > 0 for c in campaigns.values())
