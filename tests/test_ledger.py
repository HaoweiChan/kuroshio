"""No-network tests for kuroshio.core.ledger — file IO plus the realized-performance
math (rank-IC, top-k forward return, per-rating hit rate)."""

from __future__ import annotations

import logging

import pandas as pd
import pytest

from kuroshio.core import ledger

# --- append / load ------------------------------------------------------------


def test_append_then_load_round_trips_rows(tmp_path):
    path = tmp_path / "scores.jsonl"
    rows = [{"ticker": "AAA", "final_score": 0.5}, {"ticker": "BBB", "final_score": 0.6}]
    ledger.append(path, rows)
    assert ledger.load(path) == rows


def test_load_missing_file_returns_empty_list(tmp_path):
    assert ledger.load(tmp_path / "nope.jsonl") == []


def test_load_skips_a_malformed_middle_line(tmp_path, caplog):
    path = tmp_path / "scores.jsonl"
    ledger.append(path, [{"ticker": "AAA"}])
    with open(path, "a") as f:
        f.write("not valid json\n")
    ledger.append(path, [{"ticker": "BBB"}])

    with caplog.at_level(logging.WARNING):
        rows = ledger.load(path)

    assert rows == [{"ticker": "AAA"}, {"ticker": "BBB"}]
    assert any("malformed" in r.message and ":2:" in r.message for r in caplog.records)


# --- realized ------------------------------------------------------------------
#
# 11 sessions, horizon=5: date0 = index[0] (fwd window ends at index[5]), date1 =
# index[3] (fwd window ends at index[8]). Score order matches forward-return order
# for date0 (IC=+1.0) and is exactly reversed for date1 (IC=-1.0) — both perfectly
# monotonic 4-point relationships, so rank correlation is pinned exactly.

_DATES = [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2024-01-01", periods=11)]
_DATE0, _DATE1 = _DATES[0], _DATES[3]

_CLOSE = pd.DataFrame(
    {
        # position:      0    1    2    3    4    5    6    7    8    9   10
        "T1": [100.0, 100.0, 100.0, 100.0, 100.0, 110.0, 100.0, 100.0, 140.0, 100.0, 100.0],
        "T2": [100.0, 100.0, 100.0, 100.0, 100.0, 120.0, 100.0, 100.0, 130.0, 100.0, 100.0],
        "T3": [100.0, 100.0, 100.0, 100.0, 100.0, 130.0, 100.0, 100.0, 120.0, 100.0, 100.0],
        "T4": [100.0, 100.0, 100.0, 100.0, 100.0, 140.0, 100.0, 100.0, 110.0, 100.0, 100.0],
        "BENCH": [100.0, 100.0, 100.0, 100.0, 100.0, 105.0, 100.0, 100.0, 108.0, 100.0, 100.0],
    },
    index=_DATES,
)

_SCORES = [
    {"date": _DATE0, "ticker": "T1", "rank": 4, "final_score": 0.1, "fundamentals": None},
    {"date": _DATE0, "ticker": "T2", "rank": 3, "final_score": 0.2, "fundamentals": None},
    {"date": _DATE0, "ticker": "T3", "rank": 2, "final_score": 0.3, "fundamentals": None},
    {"date": _DATE0, "ticker": "T4", "rank": 1, "final_score": 0.4, "fundamentals": None},
    {"date": _DATE1, "ticker": "T1", "rank": 4, "final_score": 0.1, "fundamentals": None},
    {"date": _DATE1, "ticker": "T2", "rank": 3, "final_score": 0.2, "fundamentals": None},
    {"date": _DATE1, "ticker": "T3", "rank": 2, "final_score": 0.3, "fundamentals": None},
    {"date": _DATE1, "ticker": "T4", "rank": 1, "final_score": 0.4, "fundamentals": None},
]


def test_realized_ic_and_topk_pinned_per_date():
    result = ledger.realized(_SCORES, _CLOSE, horizon=5, benchmark="BENCH", top_k=2)

    assert result["n_dates"] == 2
    d0, d1 = result["per_date"]
    assert d0["date"] == _DATE0 and d1["date"] == _DATE1

    assert d0["ic"] == pytest.approx(1.0)
    assert d0["topk_fwd"] == pytest.approx(0.35)  # mean(T4=+0.40, T3=+0.30)
    assert d0["bench_fwd"] == pytest.approx(0.05)
    assert d0["ey_ic"] is None  # no fundamentals logged
    assert d0["rev_ic"] is None

    assert d1["ic"] == pytest.approx(-1.0)
    assert d1["topk_fwd"] == pytest.approx(0.15)  # mean(T4=+0.10, T3=+0.20)
    assert d1["bench_fwd"] == pytest.approx(0.08)
    assert d1["ey_ic"] is None
    assert d1["rev_ic"] is None

    assert result["mean_ic"] == pytest.approx(0.0)


# --- rev_ic: revision-breadth rank-IC (T8) ---------------------------------------
#
# Same 4-name / 2-date shape as _SCORES. Revision breadth (up-down)/(up+down) is
# assigned monotonically with T1<T2<T3<T4 (-0.8, -0.4, +0.4, +0.8) — matching
# date0's forward-return order exactly (IC=+1.0) and date1's reversed order
# exactly (IC=-1.0), same trick the pinned ic/topk test above uses.

_REV_FUNDAMENTALS = {
    "T1": {"eps_rev_up_30d": 1, "eps_rev_down_30d": 9},
    "T2": {"eps_rev_up_30d": 3, "eps_rev_down_30d": 7},
    "T3": {"eps_rev_up_30d": 7, "eps_rev_down_30d": 3},
    "T4": {"eps_rev_up_30d": 9, "eps_rev_down_30d": 1},
}
_REV_SCORES = [{**row, "fundamentals": _REV_FUNDAMENTALS[row["ticker"]]} for row in _SCORES]


def test_realized_rev_ic_pinned_per_date():
    result = ledger.realized(_REV_SCORES, _CLOSE, horizon=5, benchmark="BENCH", top_k=2)
    d0, d1 = result["per_date"]
    assert d0["rev_ic"] == pytest.approx(1.0)
    assert d1["rev_ic"] == pytest.approx(-1.0)
    assert result["mean_rev_ic"] == pytest.approx(0.0)


def test_realized_rev_ic_none_below_three_rows():
    rows = [
        {**_SCORES[0], "fundamentals": _REV_FUNDAMENTALS["T1"]},
        {**_SCORES[1], "fundamentals": _REV_FUNDAMENTALS["T2"]},
        {**_SCORES[2], "fundamentals": None},  # no revisions logged for T3/T4
        {**_SCORES[3], "fundamentals": None},
    ]
    result = ledger.realized(rows, _CLOSE, horizon=5, benchmark="BENCH", top_k=2)
    assert result["per_date"][0]["rev_ic"] is None
    assert result["mean_rev_ic"] is None


def test_realized_no_dates_resolve_a_horizon_returns_none_summary():
    late_date = _DATES[-1]  # nothing horizon sessions after the last row
    rows = [{"date": late_date, "ticker": "T1", "rank": 1, "final_score": 0.1, "fundamentals": None}]
    result = ledger.realized(rows, _CLOSE, horizon=5, benchmark="BENCH", top_k=2)
    assert result == {
        "per_date": [], "mean_ic": None, "mean_topk_fwd": None, "mean_excess": None,
        "beat_rate": None, "mean_ey_ic": None, "mean_rev_ic": None, "n_dates": 0,
    }


# --- rating_table ----------------------------------------------------------------

_RATING_CLOSE = pd.DataFrame(
    {
        "BUYHIT": [100.0] + [100.0] * 4 + [120.0] + [100.0] * 5,   # fwd = +0.20
        "BUYMISS": [100.0] + [100.0] * 4 + [90.0] + [100.0] * 5,   # fwd = -0.10
        "SELLHIT": [100.0] + [100.0] * 4 + [80.0] + [100.0] * 5,   # fwd = -0.20
        "HOLDHIT": [100.0] + [100.0] * 4 + [103.0] + [100.0] * 5,  # fwd = +0.03
    },
    index=_DATES,
)
_RATING_ROWS = [
    {"date": _DATES[0], "ticker": "BUYHIT", "rating": "Buy"},
    {"date": _DATES[0], "ticker": "BUYMISS", "rating": "Buy"},
    {"date": _DATES[0], "ticker": "SELLHIT", "rating": "Sell"},
    {"date": _DATES[0], "ticker": "HOLDHIT", "rating": "Hold"},
]


def test_rating_table_hit_rates_pinned():
    table = ledger.rating_table(_RATING_ROWS, _RATING_CLOSE, horizon=5)

    assert table["Buy"]["n"] == 2
    assert table["Buy"]["mean_fwd"] == pytest.approx((0.20 - 0.10) / 2)
    assert table["Buy"]["hit_rate"] == pytest.approx(0.5)  # BUYHIT hits, BUYMISS misses

    assert table["Sell"]["n"] == 1
    assert table["Sell"]["mean_fwd"] == pytest.approx(-0.20)
    assert table["Sell"]["hit_rate"] == pytest.approx(1.0)

    assert table["Hold"]["n"] == 1
    assert table["Hold"]["mean_fwd"] == pytest.approx(0.03)
    assert table["Hold"]["hit_rate"] == pytest.approx(1.0)


def test_rating_table_by_source_splits_only_when_more_than_one_source_present():
    # one source (or none at all) -> grouping unchanged, even with by_source=True
    same_source = [{**row, "source": "claude-session"} for row in _RATING_ROWS]
    assert set(ledger.rating_table(same_source, _RATING_CLOSE, horizon=5, by_source=True)) == {
        "Buy", "Sell", "Hold",
    }

    # two sources present -> keys split as "<rating> (<source>)"
    mixed = [
        {**_RATING_ROWS[0], "source": "openrouter"},   # Buy, BUYHIT, +0.20
        {**_RATING_ROWS[1], "source": "claude-session"},  # Buy, BUYMISS, -0.10
    ]
    split = ledger.rating_table(mixed, _RATING_CLOSE, horizon=5, by_source=True)
    assert split["Buy (openrouter)"] == {"n": 1, "mean_fwd": pytest.approx(0.20), "hit_rate": 1.0}
    assert split["Buy (claude-session)"] == {"n": 1, "mean_fwd": pytest.approx(-0.10), "hit_rate": 0.0}


# --- to_markdown smoke test -------------------------------------------------------


def test_to_markdown_renders_summary_and_ratings():
    summary = ledger.realized(_SCORES, _CLOSE, horizon=5, benchmark="BENCH", top_k=2)
    ratings = ledger.rating_table(_RATING_ROWS, _RATING_CLOSE, horizon=5)
    out = ledger.to_markdown(summary, ratings)
    assert "rank-IC" in out
    assert "top-k" in out
    assert "Buy" in out and "hit_rate=" in out


def test_to_markdown_shows_revision_breadth_ic_when_present():
    summary = ledger.realized(_REV_SCORES, _CLOSE, horizon=5, benchmark="BENCH", top_k=2)
    out = ledger.to_markdown(summary, ratings={})
    assert "mean revision-breadth IC=" in out


def test_a_non_session_date_resolves_to_the_next_session():
    dates = ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09"]  # Mon..Fri
    close = pd.DataFrame({"AAA": [10.0, 11.0, 12.0, 13.0, 14.0]}, index=dates)
    # rated on Sunday 2026-01-04 -> measured from Monday 10.0; horizon 2 -> 12.0
    rows = [{"date": "2026-01-04", "ticker": "AAA", "rating": "Buy"}]
    out = ledger.rating_table(rows, close, horizon=2)
    assert out["Buy"]["n"] == 1 and abs(out["Buy"]["mean_fwd"] - 0.2) < 1e-9
    # a date past the last session resolves to nothing
    assert ledger.rating_table([{"date": "2026-02-01", "ticker": "AAA", "rating": "Buy"}], close, 1) == {}


# --- stops.jsonl: the ratchet log evaluate scores against (TASK-11 #3) -----------

_STOP_ROWS = [
    {"date": _DATES[0], "ticker": "BUYHIT", "market": "us", "old": 80.0, "new": 95.0,
     "reason": "trend_add trail"},
    {"date": _DATES[8], "ticker": "BUYHIT", "market": "us", "old": 95.0, "new": 130.0,
     "reason": "trend_add trail"},
    {"date": _DATES[0], "ticker": "BUYMISS", "market": "us", "old": None, "new": 95.0,
     "reason": "trend_add trail"},
]


def test_live_stop_is_the_newest_move_at_or_before_the_date():
    assert ledger.STOPS == "stops.jsonl"
    assert ledger.live_stop(_STOP_ROWS, "BUYHIT", _DATES[0]) == 95.0
    assert ledger.live_stop(_STOP_ROWS, "BUYHIT", _DATES[7]) == 95.0   # not the 130 yet
    assert ledger.live_stop(_STOP_ROWS, "BUYHIT", _DATES[9]) == 130.0
    assert ledger.live_stop(_STOP_ROWS, "BUYHIT", "2023-01-01") is None  # before any move
    assert ledger.live_stop(_STOP_ROWS, "NOSUCH", _DATES[9]) is None


def test_rating_table_scores_the_stop_that_was_live_on_the_rating_date():
    """The point of the ledger: BUYHIT's stop was 95.00 on the rating date and 130.00
    later. Its worst close over the horizon is 100.00 — not stopped. Scoring it against
    the final 130.00 would call it stopped, which is the bug this file prevents."""
    rows = [
        {**_RATING_ROWS[0], "stop_loss": 80.0},   # BUYHIT, ratcheted to 95.00
        {**_RATING_ROWS[1], "stop_loss": None},   # BUYMISS, ratcheted to 95.00, low 90.00
    ]
    table = ledger.rating_table(rows, _RATING_CLOSE, horizon=5, stop_rows=_STOP_ROWS)
    assert table["Buy"]["n_stops"] == 2
    assert table["Buy"]["stop_hit_rate"] == pytest.approx(0.5)

    # no stop ledger -> the table is exactly what it always was
    assert "stop_hit_rate" not in ledger.rating_table(rows, _RATING_CLOSE, horizon=5)["Buy"]
