"""`kuroshio book` — the mechanical book rules over synthetic fixtures.

Fixture arithmetic (tests/fixtures/, screen date 2026-01-05, IPS position_pct 10%,
risk_budget_pct 1%, default rules: 15 core / 3 per theme / 3 attack / 5% base / 15%
attack budget / 45-day TTL):

  AAA  Widgets  Buy         stop 90 of 100 -> percent-risk 10% > base -> 5%, then attack top-up 10%
  BBB  Widgets  Overweight  no stop -> 5%, then attack top-up 10%
  CCC  Widgets  Sell        vetoed
  DDD  Widgets  Buy         stop 5 of 10 -> percent-risk 2% binds
  EEE  Gadgets  Buy 2025-10-01 -> older than the 45-day TTL -> not researched
  FFF  Gadgets  Buy 2026-01-02, earnings 2026-01-03 -> rating void
  GGG  Gizmos   Hold        5% x 0.5 PM size = 2.5%
  HHH  (none)   unrated
  III  Widgets  Buy         4th Widget -> attack sleeve at 5%
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from kuroshio.core import book as bk
from kuroshio.core.ips import parse_ips

FIX = Path(__file__).parent / "fixtures"
IPS = Path(__file__).parent.parent / "examples" / "ips-balanced.md"


@pytest.fixture
def built():
    return bk.build_book(
        bk.load_screen(FIX / "screen.json"),
        bk.load_jsonl(FIX / "ratings.jsonl"),
        parse_ips(str(IPS)),
        meta=json.loads((FIX / "meta.json").read_text()),
        scores_rows=bk.load_jsonl(FIX / "scores.jsonl"),
        positions=bk.load_positions(FIX / "positions.csv"),
        nav=100000.0,
        pm_size=json.loads((FIX / "pm_size.json").read_text()),
        locked=json.loads((FIX / "locked.json").read_text()),
    )


def _w(book, ticker):
    for rec in book["core"] + book["attack"]:
        if rec["ticker"] == ticker:
            return rec["weight"]
    raise AssertionError(f"{ticker} not in the book")


def test_core_theme_cap_pushes_the_fourth_widget_into_the_attack_sleeve(built):
    assert [r["ticker"] for r in built["core"]] == ["AAA", "BBB", "DDD", "GGG"]
    assert [r["ticker"] for r in built["attack"]] == ["III"]
    assert built["attack"][0]["theme"] == "attack"


def test_veto_ttl_and_earnings_expiry_keep_names_out(built):
    why = {r[1]: r[3] for r in built["skipped"]}
    assert why["CCC"] == "Sell"
    assert why["EEE"] == "not researched"  # rating older than the 45-day TTL
    assert why["HHH"] == "not researched"
    assert "earnings 2026-01-03 after rating 2026-01-02" in why["FFF"]


def test_weights_are_percent_risk_pm_size_and_the_attack_top_up(built):
    assert _w(built, "DDD") == 0.02  # 1% NAV / 50% stop distance
    assert _w(built, "GGG") == 0.025  # 5% base x 0.5 PM multiplier
    assert _w(built, "III") == 0.05  # overflow name at base
    assert _w(built, "AAA") == 0.10 and _w(built, "BBB") == 0.10  # attack budget top-up
    caps = {r["ticker"]: r["cap"] for r in built["core"]}
    assert caps["AAA"] == "attack 10%"
    assert caps["DDD"].startswith("percent-risk")
    assert "PM size" in caps["GGG"]


def test_locked_positions_ride_along_at_their_live_weight(built):
    (lock,) = built["locked"]
    assert lock["ticker"] == "ZZZ" and lock["weight"] == 0.09 and lock["theme"] == "locked-theme"
    assert built["gross"] == pytest.approx(0.385)
    assert built["cash"] == pytest.approx(0.615)


def test_alloc_sizes_shares_on_nav_and_lists_off_book_positions(built):
    alloc = built["alloc"]
    assert alloc["nav"] == 100000.0
    row = next(r for r in alloc["rows"] if r["ticker"] == "AAA")
    assert row["shares"] == 100 and row["usd"] == 10000 and row["have"] == 5000
    assert [s[0] for s in alloc["sells"]] == ["QQQ"]  # AAA is in the book, ZZZ is locked


def test_holdings_yaml_carries_weights_stops_and_the_locked_name(built):
    holdings = yaml.safe_load(bk.holdings_yaml(built))
    by_t = {h["ticker"]: h for h in holdings}
    assert set(by_t) == {"AAA", "BBB", "DDD", "GGG", "III", "ZZZ"}
    assert by_t["DDD"]["invalidation_price"] == 5.0
    assert by_t["ZZZ"]["theme"] == "locked-theme"
    assert by_t["AAA"]["entry_date"] == "2026-01-05"


def test_attack_floor_hold_reproduces_todays_behaviour(built):
    """AC #1: `hold` is the lowest non-vetoed rung, so it must not change anything —
    the mechanical baseline the owner traded on 2026-09-04 stays reachable."""
    assert bk.BookRules().attack_floor == "overweight"
    same = bk.build_book(
        bk.load_screen(FIX / "screen.json"),
        bk.load_jsonl(FIX / "ratings.jsonl"),
        parse_ips(str(IPS)),
        meta=json.loads((FIX / "meta.json").read_text()),
        scores_rows=bk.load_jsonl(FIX / "scores.jsonl"),
        positions=bk.load_positions(FIX / "positions.csv"),
        nav=100000.0,
        pm_size=json.loads((FIX / "pm_size.json").read_text()),
        locked=json.loads((FIX / "locked.json").read_text()),
        rules=bk.BookRules(attack_floor="hold"),
    )
    assert same["core"] == built["core"]
    assert same["attack"] == built["attack"]
    assert same["skipped"] == built["skipped"]


def test_attack_floor_skips_a_below_floor_overflow_and_the_next_name_by_rank_takes_the_slot():
    """AC #2, both branches: W2 (Hold) overflows Widgets' theme cap but sits below the
    default `overweight` floor, so W3 (Overweight) takes the one attack slot instead —
    and the core selection itself (W1) is untouched by the floor."""
    screen_rows = [
        {"ticker": "W1", "date": "2026-01-05", "rank": 1, "factors": {"close": 100.0}, "industry": "Widgets"},
        {"ticker": "W2", "date": "2026-01-05", "rank": 2, "factors": {"close": 50.0}, "industry": "Widgets"},
        {"ticker": "W3", "date": "2026-01-05", "rank": 3, "factors": {"close": 40.0}, "industry": "Widgets"},
    ]
    ratings_rows = [
        {"date": "2026-01-02", "market": "us", "ticker": "W1", "rating": "Buy"},
        {"date": "2026-01-02", "market": "us", "ticker": "W2", "rating": "Hold"},
        {"date": "2026-01-02", "market": "us", "ticker": "W3", "rating": "Overweight"},
    ]
    rules = bk.BookRules(core_n=1, core_per_theme=1, attack_n=1, attack_budget_pct=0)
    book = bk.build_book(screen_rows, ratings_rows, parse_ips(str(IPS)), rules=rules)
    assert [r["ticker"] for r in book["core"]] == ["W1"]
    assert [r["ticker"] for r in book["attack"]] == ["W3"]
    reason = {r[1]: r[3] for r in book["skipped"]}
    assert reason["W2"] == "below the attack floor (Hold)"


def test_book_md_names_the_attack_floor_in_both_languages(built):
    """AC #3: `rule_attack` in the rendered book names the floor, in en and zh."""
    for lang in ("en", "zh"):
        md = bk.render_book_md(built, lang=lang, propose_text="x")
        line = next(line for line in md.splitlines() if line.startswith("4. "))
        assert "Overweight" in line, f"{lang}: {line}"


def test_rules_are_options_not_constants():
    book = bk.build_book(
        bk.load_screen(FIX / "screen.json"),
        bk.load_jsonl(FIX / "ratings.jsonl"),
        parse_ips(str(IPS)),
        meta=json.loads((FIX / "meta.json").read_text()),
        scores_rows=bk.load_jsonl(FIX / "scores.jsonl"),
        rules=bk.BookRules(core_n=2, core_per_theme=1, attack_n=1, attack_budget_pct=0),
    )
    assert [r["ticker"] for r in book["core"]] == ["AAA", "GGG"]
    assert [r["ticker"] for r in book["attack"]] == ["BBB"]


def test_without_scores_only_the_day_ttl_applies():
    book = bk.build_book(
        bk.load_screen(FIX / "screen.json"),
        bk.load_jsonl(FIX / "ratings.jsonl"),
        parse_ips(str(IPS)),
        meta=json.loads((FIX / "meta.json").read_text()),
    )
    assert "FFF" in {r["ticker"] for r in book["core"] + book["attack"]}


def test_positions_json_and_csv_parse_to_the_same_rows(tmp_path):
    rows = bk.load_positions(FIX / "positions.csv")
    as_json = tmp_path / "positions.json"
    as_json.write_text(json.dumps(rows))
    assert bk.load_positions(as_json) == rows
    assert rows[0] == {
        "symbol": "AAA", "quantity": 50.0, "market_value": 5000.0,
        "average_price": 95.0, "asset_type": "EQUITY",
    }


def test_book_md_and_alloc_md_render_in_both_languages(built):
    for lang in ("en", "zh"):
        md = bk.render_book_md(built, lang=lang, propose_text="No proposals — portfolio is within policy.")
        assert "AAA" in md and "10.0%" in md and "{" not in md
        alloc = bk.render_alloc_md(built, lang=lang)
        assert "100,000" in alloc and "QQQ" in alloc and "{" not in alloc


def test_needs_research_orders_held_names_first_then_screen_names_by_rank():
    """AC #2: one unrated top-N name (S1), one rating voided by an earnings print (S2),
    one 24-day-old held rating (H1) and one held name 5 days before its print (H2) yield
    exactly those four entries with those reasons, held names first, then by rank."""
    screen_rows = [
        {"ticker": "H1", "date": "2026-02-01", "rank": 1, "factors": {"close": 10.0}, "industry": "X"},
        {"ticker": "H2", "date": "2026-02-01", "rank": 2, "factors": {"close": 10.0}, "industry": "X"},
        {"ticker": "S1", "date": "2026-02-01", "rank": 3, "factors": {"close": 10.0}, "industry": "X"},
        {"ticker": "S2", "date": "2026-02-01", "rank": 4, "factors": {"close": 10.0}, "industry": "X"},
    ]
    ratings_rows = [
        {"date": "2026-01-08", "market": "us", "ticker": "H1", "rating": "Buy"},
        {"date": "2026-01-25", "market": "us", "ticker": "H2", "rating": "Buy"},
        {"date": "2026-01-05", "market": "us", "ticker": "S2", "rating": "Buy"},
    ]
    scores_rows = [
        {"date": "2026-02-01", "market": "us", "ticker": "H2",
         "fundamentals": {"next_earnings_date": "2026-02-06"}},
        {"date": "2026-02-01", "market": "us", "ticker": "S2",
         "fundamentals": {"next_earnings_date": "2026-01-10"}},
    ]
    rules = bk.BookRules(core_n=10, core_per_theme=10, attack_n=0, attack_budget_pct=0)
    book = bk.build_book(
        screen_rows, ratings_rows, parse_ips(str(IPS)), scores_rows=scores_rows, rules=rules,
    )
    assert bk.needs_research(book) == {
        "asof": "2026-02-01",
        "research": [
            {"ticker": "H1", "rank": 1, "reason": "rating 24 days old", "rating_date": "2026-01-08"},
            {"ticker": "H2", "rank": 2, "reason": "earnings in 5 days", "rating_date": "2026-01-25"},
            {"ticker": "S1", "rank": 3, "reason": "not researched", "rating_date": None},
            {
                "ticker": "S2", "rank": 4,
                "reason": "rating void: earnings 2026-01-10 after rating 2026-01-05",
                "rating_date": "2026-01-05",
            },
        ],
    }


def test_needs_research_writes_an_empty_list_never_a_missing_file(tmp_path):
    """AC #3: nothing to research still writes the file, with an empty `research` list."""
    screen_rows = [{"ticker": "Z1", "date": "2026-01-05", "rank": 1, "factors": {"close": 10.0}}]
    ratings_rows = [{"date": "2026-01-02", "market": "us", "ticker": "Z1", "rating": "Buy"}]
    book = bk.build_book(screen_rows, ratings_rows, parse_ips(str(IPS)))
    assert book["skipped"] == [] and book["review"] == []
    assert bk.needs_research(book) == {"asof": "2026-01-05", "research": []}
    bk.write_book(book, tmp_path)
    assert json.loads((tmp_path / "needs_research.json").read_text()) == {
        "asof": "2026-01-05", "research": [],
    }


def test_nav_alone_still_allocates_it_is_positions_that_add_the_diff():
    """`--nav` without a positions file: the dollar allocation is a pure NAV x weight sizing,
    with nothing held to diff against (the probe's shape)."""
    book = bk.build_book(
        bk.load_screen(FIX / "screen.json"),
        bk.load_jsonl(FIX / "ratings.jsonl"),
        parse_ips(str(IPS)),
        meta=json.loads((FIX / "meta.json").read_text()),
        nav=100000.0,
    )
    alloc = book["alloc"]
    assert alloc["nav"] == 100000.0 and alloc["cash"] is None and alloc["sells"] == []
    row = next(r for r in alloc["rows"] if r["ticker"] == "AAA")
    assert row["shares"] == 100 and row["have"] == 0


def test_needs_research_stale_rating_with_a_far_off_print_is_reported_as_stale():
    # a review row carries any known earnings date; only one inside the warn window is the reason
    book = bk.build_book(
        [{"ticker": "H1", "date": "2026-02-01", "rank": 1, "factors": {"close": 10.0}, "industry": "X"}],
        [{"date": "2026-01-08", "market": "us", "ticker": "H1", "rating": "Buy"}],
        parse_ips("examples/ips-balanced.md"),
        scores_rows=[{"date": "2026-02-01", "market": "us", "ticker": "H1",
                      "fundamentals": {"next_earnings_date": "2026-04-02"}}],
        rules=bk.BookRules(core_n=10, core_per_theme=10, attack_n=0, attack_budget_pct=0),
    )
    assert [r["reason"] for r in bk.needs_research(book)["research"]] == ["rating 24 days old"]
