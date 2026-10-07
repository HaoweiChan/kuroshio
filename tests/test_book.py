"""`kuroshio book` — the mechanical book rules over synthetic fixtures.

Fixture arithmetic (tests/fixtures/, screen date 2026-01-05, IPS position_pct 10%,
risk_budget_pct 1%, default rules: 15 core / 3 per theme / 3 attack / 5% base / 30%
attack budget / 45-day TTL):

  AAA  Widgets  Buy         stop 90 of 100 -> percent-risk 10% > base -> 5%, then attack top-up 10%
  BBB  Widgets  Overweight  no stop -> 5%, then attack top-up 10%
  CCC  Widgets  Sell        vetoed
  DDD  Widgets  Buy         stop 5 of 10 -> percent-risk 2% binds, then attack top-up 4%
  EEE  Gadgets  Buy 2025-10-01 -> older than the 45-day TTL -> not researched
  FFF  Gadgets  Buy 2026-01-02, earnings 2026-01-03 -> rating void
  GGG  Gizmos   Hold        5% x 0.5 PM size = 2.5%
  HHH  (none)   unrated
  III  Widgets  Buy         4th Widget -> attack sleeve at 10%
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest
import yaml

from kuroshio.core import book as bk
from kuroshio.core.ips import parse_ips

FIX = Path(__file__).parent / "fixtures"
IPS = Path(__file__).parent.parent / "examples" / "ips-balanced.md"


def _ips(theme_pct: float = 100):
    """The example IPS with the theme budget opened up, so the fixture tests exercise the
    other rules; the theme-budget tests pass the real 20%."""
    ips = parse_ips(str(IPS))
    return dataclasses.replace(ips, caps=dataclasses.replace(ips.caps, theme_pct=theme_pct))


@pytest.fixture
def built():
    return bk.build_book(
        bk.load_screen(FIX / "screen.json"),
        bk.load_jsonl(FIX / "ratings.jsonl"),
        _ips(),
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
    assert _w(built, "DDD") == 0.04  # doubled: 2% NAV / 50% stop distance
    assert _w(built, "GGG") == 0.025  # 5% base x 0.5 PM multiplier
    assert _w(built, "III") == 0.10  # overflow name at twice base
    assert _w(built, "AAA") == 0.10 and _w(built, "BBB") == 0.10  # attack budget top-up
    caps = {r["ticker"]: r["cap"] for r in built["core"]}
    assert caps["AAA"] == "attack 10%"
    assert caps["DDD"] == "attack 4%"
    assert "PM size" in caps["GGG"]


def test_locked_positions_ride_along_at_their_live_weight(built):
    (lock,) = built["locked"]
    assert lock["ticker"] == "ZZZ" and lock["weight"] == 0.09 and lock["theme"] == "locked-theme"
    assert built["gross"] == pytest.approx(0.455)
    assert built["cash"] == pytest.approx(0.545)


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


def test_candidates_yaml_is_one_row_per_core_and_attack_name_no_locked_no_theme(built):
    """AC #1: `candidates.yml` carries core+attack only — not ZZZ, the locked name —
    each row exactly `{ticker, final_score, verdict}` with the screen's own final_score
    and the book's rating as the verdict; no `theme` key at all."""
    candidates = yaml.safe_load(bk.candidates_yaml(built))
    by_t = {c["ticker"]: c for c in candidates}
    assert set(by_t) == {"AAA", "BBB", "DDD", "GGG", "III"}  # ZZZ (locked) excluded
    assert by_t["AAA"] == {"ticker": "AAA", "final_score": 1.0, "verdict": "Buy"}
    assert by_t["GGG"] == {"ticker": "GGG", "final_score": 0.4, "verdict": "Hold"}
    assert all("theme" not in c for c in candidates)


def test_candidates_yaml_empty_book_writes_an_empty_list():
    """AC #1: a book with no core/attack names still writes valid YAML: `[]`."""
    book = bk.build_book(
        [{"ticker": "Z1", "date": "2026-01-05", "rank": 1, "factors": {"close": 10.0}}],
        [],  # no ratings -> Z1 is "not researched", skipped
        _ips(),
    )
    assert book["core"] == [] and book["attack"] == []
    assert yaml.safe_load(bk.candidates_yaml(book)) == []


def test_write_book_writes_candidates_yaml_and_returns_its_path(tmp_path, built):
    written = bk.write_book(built, tmp_path)
    assert tmp_path / "candidates.yml" in written
    candidates = yaml.safe_load((tmp_path / "candidates.yml").read_text())
    assert {c["ticker"] for c in candidates} == {"AAA", "BBB", "DDD", "GGG", "III"}


def test_book_candidates_give_the_actual_pass_a_swap_challenger(tmp_path, built):
    """AC #2: `_run_propose` (the shared core of `propose`) run on an actual-portfolio
    holdings file, with the book's own `candidates.yml` as `--candidates`, issues a SWAP
    naming the weak incumbent and the book's strongest challenger — no network, every
    score hand-typed."""
    from kuroshio import cli

    candidates_path = tmp_path / "candidates.yml"
    candidates_path.write_text(bk.candidates_yaml(built))
    holdings_path = tmp_path / "holdings.yml"
    holdings_path.write_text("- {ticker: WEAK, weight: 0.05, score: 0.40}\n")

    cards, problems = cli._run_propose(
        str(IPS), str(holdings_path), "us", candidates_path=str(candidates_path),
    )
    assert problems is None
    swap = next(c for c in cards if c.action == "SWAP")
    assert swap.sell == "WEAK" and swap.buy == "AAA"  # AAA: final_score 1.0, the strongest


def test_book_candidate_already_held_is_not_offered_as_a_swap(tmp_path, built):
    """AC #2: a book name already sitting in the actual portfolio is not proposed —
    the next-strongest challenger (BBB) takes the slot instead."""
    from kuroshio import cli

    candidates_path = tmp_path / "candidates.yml"
    candidates_path.write_text(bk.candidates_yaml(built))
    holdings_path = tmp_path / "holdings.yml"
    holdings_path.write_text(
        "- {ticker: WEAK, weight: 0.05, score: 0.40}\n"
        "- {ticker: AAA, weight: 0.05, score: 0.95}\n"
    )

    cards, problems = cli._run_propose(
        str(IPS), str(holdings_path), "us", candidates_path=str(candidates_path),
    )
    assert problems is None
    assert all(c.buy != "AAA" for c in cards)  # AAA is already held, not a challenger
    swap = next(c for c in cards if c.action == "SWAP")
    assert swap.sell == "WEAK" and swap.buy == "BBB"


def test_attack_floor_hold_reproduces_todays_behaviour(built):
    """AC #1: `hold` is the lowest non-vetoed rung, so it must not change anything —
    the mechanical baseline the owner traded on 2026-09-04 stays reachable."""
    assert bk.BookRules().attack_floor == "overweight"
    same = bk.build_book(
        bk.load_screen(FIX / "screen.json"),
        bk.load_jsonl(FIX / "ratings.jsonl"),
        _ips(),
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
    rules = bk.BookRules(core_n=1, core_per_theme=1, attack_n=1, attack_budget_pct=10)
    book = bk.build_book(screen_rows, ratings_rows, _ips(), rules=rules)
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
        _ips(),
        meta=json.loads((FIX / "meta.json").read_text()),
        scores_rows=bk.load_jsonl(FIX / "scores.jsonl"),
        rules=bk.BookRules(core_n=2, core_per_theme=1, attack_n=1, attack_budget_pct=10),
    )
    assert [r["ticker"] for r in book["core"]] == ["AAA", "GGG"]
    assert [r["ticker"] for r in book["attack"]] == ["BBB"]


def test_without_scores_only_the_day_ttl_applies():
    book = bk.build_book(
        bk.load_screen(FIX / "screen.json"),
        bk.load_jsonl(FIX / "ratings.jsonl"),
        _ips(),
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
        screen_rows, ratings_rows, _ips(), scores_rows=scores_rows, rules=rules,
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
    book = bk.build_book(screen_rows, ratings_rows, _ips())
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
        _ips(),
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


def test_a_name_closing_at_or_below_its_rating_stop_is_dropped_not_given_base_weight():
    """AAA closes at 100 with a Buy and stop 90. Moving the stop to 100 (touched) or 120
    (through it) must drop AAA; before this, target_weight read stop >= entry as "no stop"
    and handed the name full base weight."""
    screen = bk.load_screen(FIX / "screen.json")
    for stop in (100.0, 120.0):
        ratings = [
            {**r, "stop_loss": stop} if r["ticker"] == "AAA" else r
            for r in bk.load_jsonl(FIX / "ratings.jsonl")
        ]
        book = bk.build_book(screen, ratings, _ips(),
                             meta=json.loads((FIX / "meta.json").read_text()))
        assert "AAA" not in {r["ticker"] for r in book["core"] + book["attack"]}
        assert {r[1]: r[3] for r in book["skipped"]}["AAA"] == f"Buy below its stop {stop:.2f}"


def _budget_book(ips, themes=None):
    return bk.build_book(
        bk.load_screen(FIX / "screen.json"), bk.load_jsonl(FIX / "ratings.jsonl"), ips,
        meta=json.loads((FIX / "meta.json").read_text()),
        scores_rows=bk.load_jsonl(FIX / "scores.jsonl"),
        positions=bk.load_positions(FIX / "positions.csv"), nav=100000.0,
        pm_size=json.loads((FIX / "pm_size.json").read_text()),
        locked=json.loads((FIX / "locked.json").read_text()), themes=themes,
    )


def test_the_attack_top_up_stops_at_the_ips_theme_budget():
    """Widgets at 25%: AAA 5 + BBB 5 + DDD 2 + III 10 leaves 3% for the AAA top-up."""
    book = _budget_book(_ips(theme_pct=25))
    assert (_w(book, "AAA"), _w(book, "BBB"), _w(book, "III")) == (0.08, 0.05, 0.10)
    assert {r["ticker"]: r["cap"] for r in book["core"]}["AAA"] == "attack 8%"
    widgets = sum(r["weight"] for r in book["core"] + book["attack"] if r["industry"] == "Widgets")
    assert widgets == pytest.approx(0.25)


def test_a_locked_position_spends_its_theme_budget_first_and_the_themes_map_names_the_theme():
    """ZZZ is locked at 9% in 'locked-theme'; mapping III there leaves it the budget's rest."""
    ips = _ips()
    for cap, expect in ((9.5, None), (12, 0.03)):
        tight = dataclasses.replace(ips, caps=dataclasses.replace(ips.caps, theme_caps={"locked-theme": cap}))
        book = _budget_book(tight, themes={"III": "locked-theme"})
        if expect is None:
            assert {r[1]: r[3] for r in book["skipped"]}["III"] == "theme budget full (locked-theme 9.5%)"
        else:
            assert _w(book, "III") == expect
            assert "theme: locked-theme" in bk.holdings_yaml(book)
            assert "theme: locked-theme" in bk.candidates_yaml(book)


def test_a_name_that_broke_its_stop_since_the_rating_waits_for_a_new_rating():
    """AAA: Buy on 2026-01-02, stop 90, screen close 100 on 2026-01-05. A close of 89 on
    01-02 itself is the rating's own session (the stop was set after it) and does not count;
    89 on 01-03 does, even though the name is back at 100 today."""
    screen, ratings = bk.load_screen(FIX / "screen.json"), bk.load_jsonl(FIX / "ratings.jsonl")

    def build(history):
        return bk.build_book(screen, ratings, _ips(), meta=json.loads((FIX / "meta.json").read_text()),
                             closes={"AAA": history})

    assert "AAA" in {r["ticker"] for r in build({"2026-01-02": 89.0, "2026-01-05": 100.0})["core"]}
    book = build({"2026-01-02": 95.0, "2026-01-03": 89.0, "2026-01-05": 100.0})
    assert "AAA" not in {r["ticker"] for r in book["core"] + book["attack"]}
    assert {r[1]: r[3] for r in book["skipped"]}["AAA"] == "Buy stopped out 2026-01-03; needs a new rating"
    queue = {r["ticker"]: r["reason"] for r in bk.needs_research(book)["research"]}
    assert queue["AAA"] == "stopped out 2026-01-03; needs a new rating"


def _one_theme_screen(n: int = 7):
    """T1..Tn, one industry, all Buy: with 1 core slot per theme T1 is core, the rest overflow."""
    screen = [{"ticker": f"T{i}", "date": "2026-01-05", "rank": i, "final_score": 1 - i / 100,
               "factors": {"close": 100.0}, "industry": "X"} for i in range(1, n + 1)]
    ratings = [{"date": "2026-01-02", "market": "us", "ticker": f"T{i}", "rating": "Buy"}
               for i in range(1, n + 1)]
    return screen, ratings


def test_an_overflow_incumbent_keeps_its_attack_slot_inside_the_buffer_only():
    """1 attack slot, buffer 2 -> the first two overflow candidates (T2, T3) are 'inside'."""
    screen, ratings = _one_theme_screen()
    rules = bk.BookRules(core_n=1, core_per_theme=1, attack_n=1, attack_budget_pct=5.0)

    def attack(prev):
        book = bk.build_book(screen, ratings, _ips(), rules=rules, prev_book=prev)
        return [r["ticker"] for r in book["attack"]], {r[1]: r[3] for r in book["skipped"]}

    assert attack(None)[0] == ["T2"]                                   # no history: best rank
    names, why = attack({"attack": [{"ticker": "T3"}], "core": []})
    assert names == ["T3"] and why["T2"] == "Buy attack slot kept by T3 (hysteresis)"
    assert attack({"attack": [{"ticker": "T4"}], "core": []})[0] == ["T2"]  # T4 is outside the buffer


def test_a_doubled_incumbent_keeps_the_top_up_inside_the_buffer(built):
    """Fixture, 15% attack budget: III's overflow slot uses 10%, one doubling is left. By rank it
    goes to AAA; with BBB doubled yesterday (and inside 2 x 1 eligible names) BBB keeps it."""
    rules = bk.BookRules(attack_budget_pct=15.0)

    def doubled(prev):
        book = bk.build_book(
            bk.load_screen(FIX / "screen.json"), bk.load_jsonl(FIX / "ratings.jsonl"), _ips(),
            meta=json.loads((FIX / "meta.json").read_text()),
            scores_rows=bk.load_jsonl(FIX / "scores.jsonl"),
            pm_size=json.loads((FIX / "pm_size.json").read_text()), rules=rules, prev_book=prev)
        return [r["ticker"] for r in book["core"] if r.get("sleeve") == "attack"]

    assert doubled(None) == ["AAA"]
    assert doubled({"attack": [], "core": [{"ticker": "BBB", "sleeve": "attack"}]}) == ["BBB"]
    assert doubled({"attack": [], "core": [{"ticker": "GGG", "sleeve": "attack"}]}) == ["AAA"]  # PM-capped


def test_previous_book_is_the_newest_dated_dir_before_asof(tmp_path):
    for day in ("2026-01-02", "2026-01-05", "run"):
        (tmp_path / day).mkdir()
        (tmp_path / day / "book.json").write_text(json.dumps({"asof": day}))
    assert bk.previous_book(tmp_path, "2026-01-05")["asof"] == "2026-01-02"
    assert bk.previous_book(tmp_path, "2026-01-02") is None


def test_a_wide_stop_shrinks_the_top_up_instead_of_forbidding_it():
    """DDD's stop is 50% away, so its risk-sized weight is 2%. With budget left after III, AAA and
    BBB, its top-up is 2 x that = 4% — before, a percent-risk name was never doubled at all, so
    a name crossing the 20% stop-distance line flipped between 10% and under 5% day to day."""
    book = bk.build_book(
        bk.load_screen(FIX / "screen.json"), bk.load_jsonl(FIX / "ratings.jsonl"), _ips(),
        meta=json.loads((FIX / "meta.json").read_text()),
        scores_rows=bk.load_jsonl(FIX / "scores.jsonl"),
        pm_size=json.loads((FIX / "pm_size.json").read_text()),
        rules=bk.BookRules(attack_budget_pct=25.0))
    caps = {r["ticker"]: r["cap"] for r in book["core"]}
    assert (_w(book, "AAA"), _w(book, "BBB"), _w(book, "DDD")) == (0.10, 0.10, 0.04)
    assert caps["DDD"] == "attack 4%" and "PM size" in caps["GGG"]  # the PM cut is still not doubled


def _wide_screen(n: int = 6, stop: float | None = None):
    """T1..Tn, one industry each, all Buy at 100 — nothing but the sizing rules binds."""
    screen = [{"ticker": f"T{i}", "date": "2026-01-05", "rank": i, "final_score": 1 - i / 100,
               "factors": {"close": 100.0}, "industry": f"I{i}"} for i in range(1, n + 1)]
    ratings = [{"date": "2026-01-02", "market": "us", "ticker": f"T{i}", "rating": "Buy",
                **({"stop_loss": stop} if stop else {})} for i in range(1, n + 1)]
    return screen, ratings


def test_the_tier_sizes_the_top_names_on_its_own_base_and_risk_budget():
    rules = bk.BookRules(attack_budget_pct=0.0, tier_n=2)
    book = bk.build_book(*_wide_screen(), _ips(), rules=rules)
    assert [(r["ticker"], r["weight"], r.get("tier", False)) for r in book["core"][:3]] == [
        ("T1", 0.075, True), ("T2", 0.075, True), ("T3", 0.05, False)]
    # a 20% stop: 1.35% / 20% = 6.75% for the tier, 1% / 20% = 5% for the rest
    book = bk.build_book(*_wide_screen(stop=80.0), _ips(), rules=rules)
    assert [_w(book, t) for t in ("T1", "T3")] == [0.0675, 0.05]
    assert book["core"][0]["cap"] == "percent-risk (1.35% NAV / 20% stop)"
    # off by default
    assert _w(bk.build_book(*_wide_screen(), _ips()), "T1") == 0.1  # plain 5%, attack-doubled


def test_a_tier_incumbent_keeps_the_tier_inside_the_buffer_only():
    """tier 2, buffer 2 -> yesterday's tier names stay while inside the top 4 core names."""
    rules = bk.BookRules(attack_budget_pct=0.0, tier_n=2)

    def tier(*held):
        prev = {"attack": [], "core": [{"ticker": t, "tier": True} for t in held]}
        book = bk.build_book(*_wide_screen(), _ips(), rules=rules, prev_book=prev)
        return [r["ticker"] for r in book["core"] if r.get("tier")]

    assert tier() == ["T1", "T2"]
    assert tier("T4") == ["T1", "T4"]          # inside the buffer: kept, the rest by rank
    assert tier("T5") == ["T1", "T2"]          # outside: back to the plain tier


def test_gross_never_passes_100_percent_and_the_lowest_ranks_give_way():
    rules = bk.BookRules(base_pct=10.0, attack_budget_pct=0.0)
    book = bk.build_book(*_wide_screen(12), _ips(), rules=rules)
    assert book["gross"] == pytest.approx(1.0)
    assert [r["ticker"] for r in book["core"]] == [f"T{i}" for i in range(1, 11)]
    assert {r[1]: r[3] for r in book["skipped"]}["T12"] == "Buy gross cap 100%"


@pytest.mark.parametrize(("stop", "weight", "cap"), [
    (90.0, 0.10, "attack 10%"),
    (67.0, 0.0606, "percent-risk (2% NAV / 33% stop)"),
])
def test_overflow_uses_twice_base_and_twice_risk_budget(stop, weight, cap):
    screen, ratings = _one_theme_screen(2)
    ratings[1]["stop_loss"] = stop
    rules = bk.BookRules(core_n=1, core_per_theme=1, attack_n=1)
    book = bk.build_book(screen, ratings, _ips(), rules=rules)
    assert book["attack"][0]["weight"] == weight
    assert book["attack"][0]["cap"] == cap
    reduced = bk.build_book(screen, ratings, _ips(), rules=rules, pm_size={"T2": 0.5})
    assert reduced["attack"][0]["weight"] == round(weight * 0.5, 4)
    assert reduced["attack"][0]["cap"] == f"{cap} x 0.5 (PM size)"


@pytest.mark.parametrize(("budget", "weights"), [
    (0.0, []), (0.5, []), (10.5, [0.10]), (15.0, [0.10, 0.05]),
    (15.555, [0.10, 0.0555]), (30.0, [0.10, 0.10, 0.10]), (35.0, [0.10, 0.10, 0.10]),
])
def test_overflow_and_core_top_ups_never_overspend_attack_budget(budget, weights):
    rules = bk.BookRules(core_n=1, core_per_theme=1, attack_n=3, attack_budget_pct=budget)
    book = bk.build_book(*_one_theme_screen(), _ips(), rules=rules)
    assert [r["weight"] for r in book["attack"]] == weights
    spent = sum(weights) + sum(r["weight"] - 0.05 for r in book["core"])
    assert spent <= budget / 100 + 1e-9
    if weights and weights[-1] < 0.10:
        assert book["attack"][-1]["cap"] == "attack budget"


def test_no_map_outputs_are_byte_identical(built):
    """Digest captured from the gate-green worktree before the vehicle feature."""
    import hashlib

    from kuroshio.site.labels import labels
    from kuroshio.site.render import _alloc_page, _book_page

    texts = [json.dumps(built, sort_keys=True), bk.holdings_yaml(built), bk.candidates_yaml(built)]
    for lang in ("en", "zh"):
        texts += [bk.render_book_md(built, lang), bk.render_alloc_md(built, lang),
                  _book_page(built, "", {}, labels(lang), str), _alloc_page(built, labels(lang), str)]
    assert hashlib.sha256("\n".join(texts).encode()).hexdigest() == (
        "6457f22318b7352022a9f1f325b9e1c9a164f238eb0d8b815d7496557b708d9f"
    )


@pytest.mark.parametrize("quote", [None, 37.0])
def test_leverage_changes_vehicle_and_exposure_only(built, tmp_path, quote):
    from kuroshio import cli
    from kuroshio.site.render import render_site

    positions = bk.load_positions(FIX / "positions.csv")
    positions.append(dict(symbol="AAAU", quantity=10, market_value=370,
                          average_price=37, asset_type="ETF"))
    book = bk.build_book(
        bk.load_screen(FIX / "screen.json"), bk.load_jsonl(FIX / "ratings.jsonl"), _ips(),
        meta=bk.load_json(FIX / "meta.json"), scores_rows=bk.load_jsonl(FIX / "scores.jsonl"),
        positions=positions, nav=100000, pm_size=bk.load_json(FIX / "pm_size.json"),
        locked=bk.load_json(FIX / "locked.json"),
        leverage_map={"AAA": "AAAU", "III": "IIIU", "GGG": "GGGU", "ZZZ": "ZZZU"},
        closes={"AAAU": {"2026-01-05": quote}, "IIIU": {"2026-01-04": 37}},
        prev_book=built,
    )
    for sleeve in ("core", "attack", "locked"):
        for old, new in zip(built[sleeve], book[sleeve], strict=True):
            if old["ticker"] in {"AAA", "III"}:
                assert new == dict(old, vehicle=old["ticker"] + "U", leverage=2,
                                   exposure=2 * old["weight"])
            else:
                assert new == old  # unmapped attack BBB/DDD; mapped non-attack GGG and locked ZZZ
    assert book["gross"] == built["gross"] and book["cash"] == built["cash"]
    assert book["exposure"] == pytest.approx(built["gross"] + 0.2)
    assert bk.candidates_yaml(book) == bk.candidates_yaml(built)
    assert bk.concentration(book) == bk.concentration(built)
    assert book["ips"] == built["ips"]
    aaa = next(r for r in book["alloc"]["rows"] if r["ticker"] == "AAA")
    assert aaa["vehicle"] == "AAAU" and aaa["exposure"] == 0.2 and aaa["leverage"] == 2
    assert aaa["entry"] == 100 and aaa["vehicle_price"] == quote
    assert aaa["shares"] == (270 if quote else None)
    assert aaa["usd"] == (9990 if quote else 10000) and aaa["have"] == 370
    iii = next(r for r in book["alloc"]["rows"] if r["ticker"] == "III")
    assert iii["shares"] is None  # a stale quote is not the book-date ETF close
    assert {r[0] for r in book["alloc"]["sells"]} == {"AAA", "QQQ"}
    holdings = yaml.safe_load(bk.holdings_yaml(book))
    old_holdings = yaml.safe_load(bk.holdings_yaml(built))
    for old, new in zip(old_holdings, holdings, strict=True):
        assert {k: v for k, v in new.items() if k not in {"vehicle", "exposure"}} == old
    assert holdings[0]["vehicle"] == "AAAU" and holdings[0]["exposure"] == 0.2
    out = tmp_path / "book"
    bk.write_book(book, out)
    assert json.loads((out / "book.json").read_text())["core"][0]["leverage"] == 2
    handoff = cli._holdings_from_yaml(str(out / "holdings.yml"))
    assert handoff[0].ticker == "AAA" and handoff[0].leverage == 1
    site = tmp_path / "site"
    render_site(out, FIX / "reports", site)
    for lang, prefix, label in (("en", "", "Exposure"), ("zh", "zh/", "曝險")):
        for text in (bk.render_book_md(book, lang), bk.render_alloc_md(book, lang),
                     (site / prefix / "index.html").read_text(),
                     (site / prefix / "alloc.html").read_text()):
            assert "2x AAAU" in text and "2x IIIU" in text and f"{label}: 20.0%" in text
            assert "2x GGGU" not in text
        html = (site / prefix / "alloc.html").read_text()
        assert "reports/AAA/2026-01-02.html" in html and "<td>n/a</td>" in html


@pytest.mark.parametrize("theme_pct", [20, 100])
@pytest.mark.parametrize("stop", [67, 90])
def test_leverage_keeps_cap_decisions_and_gross_cut(theme_pct, stop):
    screen, ratings = _wide_screen(15, stop=stop)
    # Repeated industries exercise overflow, theme/risk/attack caps, and the gross cut.
    for i, row in enumerate(screen):
        row["industry"] = f"I{i // 3}"
    rules = bk.BookRules(core_per_theme=1, attack_n=10, base_pct=10, attack_budget_pct=80)
    plain = bk.build_book(screen, ratings, _ips(theme_pct), rules=rules)
    leveraged = bk.build_book(screen, ratings, _ips(theme_pct), rules=rules,
                             leverage_map={r["ticker"]: r["ticker"] + "U" for r in screen})
    assert leveraged.pop("exposure") >= leveraged["gross"]
    for row in leveraged["core"] + leveraged["attack"]:
        if "vehicle" in row:
            assert row.pop("exposure") == 2 * row["weight"]
            assert row.pop("leverage") == 2
            row.pop("vehicle")
    assert leveraged == plain
    if theme_pct == 100 and stop == 90:
        assert plain["gross"] == pytest.approx(1)
        assert any("gross cap" in r[3] for r in plain["skipped"])


@pytest.mark.parametrize("price", [25, 0, -1, float("nan")])
def test_alloc_uses_screen_etf_close_or_na(price):
    screen, ratings = _wide_screen(1)
    screen.append(dict(ticker="T1U", date=screen[0]["date"], rank=2, factors={"close": price}))
    book = bk.build_book(screen, ratings, _ips(), nav=100000, leverage_map={"T1": "T1U"})
    row = book["alloc"]["rows"][0]
    assert row["shares"] == (400 if price == 25 else None)
    assert row["entry"] == 100
