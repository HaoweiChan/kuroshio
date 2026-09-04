"""No-network tests for kuroshio.cli's --members-file support: point-in-time
membership loading, the asof lookup rule, the screen-wrapping decorator, and one
end-to-end `simulate` run proving an excluded ticker never ends up held."""

from __future__ import annotations

import pytest

from kuroshio.cli import _load_members, _members_at, _pit_screen
from kuroshio.core.screening import us
from kuroshio.core.simulate import simulate
from tests.test_allocator import cand, make_ips
from tests.test_simulate import RATES, TICKERS, _ascending_panel

MEMBERS_CSV = "date,tickers\n2020-01-01,AAA BBB\n2020-06-01,BBB CCC\n2021-01-01,CCC DDD\n"


def test_load_members_returns_ascending_snapshots(tmp_path):
    f = tmp_path / "members.csv"
    f.write_text(MEMBERS_CSV)
    snapshots = _load_members(str(f))
    assert [d for d, _ in snapshots] == ["2020-01-01", "2020-06-01", "2021-01-01"]
    assert snapshots[0][1] == frozenset({"AAA", "BBB"})
    assert snapshots[1][1] == frozenset({"BBB", "CCC"})
    assert snapshots[2][1] == frozenset({"CCC", "DDD"})


def test_members_at_before_on_between_and_after(tmp_path):
    f = tmp_path / "members.csv"
    f.write_text(MEMBERS_CSV)
    snapshots = _load_members(str(f))

    assert _members_at(snapshots, "2019-01-01") == frozenset({"AAA", "BBB"})  # before first
    assert _members_at(snapshots, "2020-06-01") == frozenset({"BBB", "CCC"})  # exactly on
    assert _members_at(snapshots, "2020-09-01") == frozenset({"BBB", "CCC"})  # between
    assert _members_at(snapshots, "2022-01-01") == frozenset({"CCC", "DDD"})  # after last


def test_load_members_rejects_empty_file(tmp_path):
    f = tmp_path / "empty.csv"
    f.write_text("")
    with pytest.raises(ValueError):
        _load_members(str(f))


def test_load_members_rejects_wrong_header(tmp_path):
    f = tmp_path / "bad.csv"
    f.write_text("ticker,date\nAAA,2020-01-01\n")
    with pytest.raises(ValueError):
        _load_members(str(f))


def test_pit_screen_keeps_only_members_and_preserves_order_and_ranks():
    candidates = [cand("A", 0.9), cand("B", 0.8), cand("C", 0.7)]
    for i, c in enumerate(candidates, start=1):
        c.rank = i

    def stub_screen(panel, asof=None, **kw):
        return candidates

    snapshots = [("2020-01-01", frozenset({"A", "C"}))]
    wrapped = _pit_screen(stub_screen, snapshots)
    out = wrapped(panel=None, asof="2020-06-01")

    assert [c.ticker for c in out] == ["A", "C"]
    assert [c.rank for c in out] == [1, 3]


def test_pit_screen_defaults_asof_to_panels_last_index_label():
    seen = {}

    def stub_screen(panel, asof=None, **kw):
        seen["asof"] = asof
        return [cand("A", 0.9)]

    panel = _ascending_panel()
    snapshots = [("1900-01-01", frozenset({"A"}))]
    wrapped = _pit_screen(stub_screen, snapshots)
    out = wrapped(panel)

    assert seen["asof"] is None  # unresolved asof passed through to screen_fn unchanged
    assert [c.ticker for c in out] == ["A"]


def test_simulate_with_a_members_wrapper_never_holds_the_excluded_ticker():
    panel = _ascending_panel()
    excluded = TICKERS[RATES.index(max(RATES))]  # top-rate ticker, always the strongest pick
    snapshots = [("1900-01-01", frozenset(TICKERS) - {excluded})]
    screen_fn = _pit_screen(us.screen, snapshots)

    ips = make_ips()
    result = simulate(panel, screen_fn, us.score_names, ips, "us", benchmark="SPY", top_k=5, step=5)

    assert excluded not in result.summary()["final_holdings"]
    assert all(excluded not in row for row in result.weights)
