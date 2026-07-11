import pytest

from kuroshio.agents.facets import FacetStore, TTL_DAYS


def test_put_get_roundtrip(tmp_path):
    store = FacetStore(tmp_path)
    store.put("2330", "technical", "line up, buy the dip", asof="2026-07-10")
    assert store.get("2330", "technical", "2026-07-10") == "line up, buy the dip"


def test_fundamentals_ttl_7_days(tmp_path):
    store = FacetStore(tmp_path)
    store.put("2330", "fundamentals", "solid balance sheet", asof="2026-07-01")
    assert store.get("2330", "fundamentals", "2026-07-07") == "solid balance sheet"  # D+6
    assert store.get("2330", "fundamentals", "2026-07-09") is None  # D+8


def test_news_default_ttl_1_day(tmp_path):
    store = FacetStore(tmp_path)
    store.put("2330", "news", "earnings beat", asof="2026-07-01")
    assert store.get("2330", "news", "2026-07-01") == "earnings beat"  # same day
    assert store.get("2330", "news", "2026-07-02") is None  # D+1, already expired


def test_future_report_not_returned(tmp_path):
    store = FacetStore(tmp_path)
    store.put("2330", "news", "leaked report", asof="2026-07-10")
    assert store.get("2330", "news", "2026-07-05") is None


def test_same_day_overwrite_idempotent(tmp_path):
    store = FacetStore(tmp_path)
    p1 = store.put("2330", "chips", "first draft", asof="2026-07-10")
    p2 = store.put("2330", "chips", "revised draft", asof="2026-07-10")
    assert p1 == p2
    entries = list((tmp_path / "2330").glob("chips-*.md"))
    assert len(entries) == 1
    assert store.get("2330", "chips", "2026-07-10") == "revised draft"


def test_invalidate_per_facet_and_whole_ticker(tmp_path):
    store = FacetStore(tmp_path)
    store.put("2330", "technical", "t", asof="2026-07-10")
    store.put("2330", "chips", "c", asof="2026-07-10")
    store.put("2330", "news", "n", asof="2026-07-10")

    assert store.invalidate("2330", "chips") == 1
    assert store.get("2330", "chips", "2026-07-10") is None
    assert store.get("2330", "technical", "2026-07-10") == "t"  # untouched

    assert store.invalidate("2330") == 2  # technical + news
    assert store.get("2330", "technical", "2026-07-10") is None
    assert store.get("2330", "news", "2026-07-10") is None


def test_invalidate_missing_ticker_dir(tmp_path):
    store = FacetStore(tmp_path)
    assert store.invalidate("9999") == 0


def test_corrupt_file_returns_none(tmp_path):
    store = FacetStore(tmp_path)
    store.put("2330", "sentiment", "fine", asof="2026-07-10")
    # clobber with garbage that isn't valid frontmatter/yaml
    path = tmp_path / "2330" / "sentiment-2026-07-10.md"
    path.write_bytes(b"\x00\x01 not even close to frontmatter ---")
    assert store.get("2330", "sentiment", "2026-07-10") is None


def test_path_traversal_ticker_rejected(tmp_path):
    store = FacetStore(tmp_path)
    with pytest.raises(ValueError):
        store.put("../x", "technical", "content", asof="2026-07-10")
    with pytest.raises(ValueError):
        store.get("../x", "technical", "2026-07-10")


def test_path_traversal_facet_rejected(tmp_path):
    store = FacetStore(tmp_path)
    with pytest.raises(ValueError):
        store.put("2330", "../x", "content", asof="2026-07-10")


def test_plan_marks_fresh_vs_stale(tmp_path):
    store = FacetStore(tmp_path)
    # 2330: technical fresh at asof, news stale (expired)
    store.put("2330", "technical", "2330 tech", asof="2026-07-10")
    store.put("2330", "news", "2330 news", asof="2026-07-01")  # long expired by 07-10
    # 2454: nothing cached at all
    result = store.plan(["2330", "2454"], ["technical", "news"], asof="2026-07-10")

    assert result == {
        "2330": {"technical": "2330 tech", "news": None},
        "2454": {"technical": None, "news": None},
    }


def test_ttl_days_table():
    assert TTL_DAYS == {
        "technical": 1,
        "chips": 1,
        "sentiment": 1,
        "news": 1,
        "fundamentals": 7,
    }
