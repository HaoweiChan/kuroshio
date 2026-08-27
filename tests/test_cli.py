"""No-network tests for kuroshio.cli — arg parsing, YAML helpers, and the
propose/ips-validate commands end-to-end via main(). `screen` is only
exercised for its argument-error path here; the network path is untested
by design (no network in this repo's test suite)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from kuroshio.cli import (
    _candidates_from_yaml,
    _holdings_from_yaml,
    _parse_tickers,
    _score_missing,
    main,
)
from kuroshio.core.screening import get_profile
from kuroshio.types import Candidate, Holding, Panel

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


# --- pure helpers --------------------------------------------------------


def test_parse_tickers_from_comma_string():
    assert _parse_tickers("AAPL, MSFT ,, NVDA", None) == ["AAPL", "MSFT", "NVDA"]


def test_parse_tickers_from_file_with_comments(tmp_path):
    f = tmp_path / "tickers.txt"
    f.write_text("AAPL\n# a comment\nMSFT  # inline note\n\nNVDA\n")
    assert _parse_tickers(None, str(f)) == ["AAPL", "MSFT", "NVDA"]


def test_holdings_from_yaml(tmp_path):
    f = tmp_path / "holdings.yml"
    f.write_text("- {ticker: AAPL, weight: 0.1, theme: tech, score: 0.5}\n- {ticker: TSM, weight: 0.05}\n")
    holdings = _holdings_from_yaml(str(f))
    assert holdings == [
        Holding(ticker="AAPL", weight=0.1, theme="tech", score=0.5),
        Holding(ticker="TSM", weight=0.05),
    ]


def test_candidates_from_yaml_builds_verdicts_and_themes(tmp_path):
    f = tmp_path / "candidates.yml"
    f.write_text(
        "- {ticker: NEW, final_score: 0.9, theme: ai, verdict: buy}\n"
        "- {ticker: OTHER, final_score: 0.7}\n"
    )
    candidates, verdicts, themes = _candidates_from_yaml(str(f))
    assert [c.ticker for c in candidates] == ["NEW", "OTHER"]
    assert all(isinstance(c, Candidate) for c in candidates)
    assert verdicts == {"NEW": "buy"}
    assert themes == {"NEW": "ai"}


# --- screen: arg-parsing only, no network -----------------------------------


def test_screen_requires_tickers_flag(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["screen", "--market", "us"])
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "--tickers" in err


# --- ips-validate end-to-end -------------------------------------------------


def test_ips_validate_ok(capsys):
    code = main(["ips-validate", str(EXAMPLES / "ips-balanced.md")])
    out = capsys.readouterr().out
    assert code == 0
    assert "OK" in out
    assert "risk_profile=balanced" in out


def test_ips_validate_reports_problems(tmp_path, capsys):
    bad = tmp_path / "bad.md"
    bad.write_text("---\nversion: 2\n---\nbody\n")
    code = main(["ips-validate", str(bad)])
    out = capsys.readouterr().out
    assert code == 2
    assert "version" in out


# --- propose end-to-end -------------------------------------------------------


def test_propose_emits_trim_card_for_hard_cap_breach(tmp_path, capsys):
    holdings = tmp_path / "holdings.yml"
    holdings.write_text("- {ticker: OVER, weight: 0.30, score: 0.5}\n")

    code = main(
        [
            "propose",
            "--ips", str(EXAMPLES / "ips-balanced.md"),
            "--holdings", str(holdings),
            "--market", "us",
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "TRIM OVER" in out
    assert "position_hard_pct" in out


def test_propose_no_candidates_still_runs(tmp_path, capsys):
    holdings = tmp_path / "holdings.yml"
    holdings.write_text("- {ticker: OK, weight: 0.05, score: 0.5}\n")

    code = main(
        [
            "propose",
            "--ips", str(EXAMPLES / "ips-balanced.md"),
            "--holdings", str(holdings),
            "--market", "us",
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "No proposals" in out


def test_propose_with_candidates_swap(tmp_path, capsys):
    holdings = tmp_path / "holdings.yml"
    holdings.write_text("- {ticker: WEAK, weight: 0.05, score: 0.40}\n")
    candidates = tmp_path / "candidates.yml"
    candidates.write_text("- {ticker: GOOD, final_score: 0.60, verdict: buy}\n")

    code = main(
        [
            "propose",
            "--ips", str(EXAMPLES / "ips-balanced.md"),
            "--holdings", str(holdings),
            "--candidates", str(candidates),
            "--market", "us",
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "SWAP WEAK → GOOD" in out
    assert "Auto-filled" not in out  # both scores hand-typed -> nothing to disclose


def test_propose_exits_2_on_invalid_ips(tmp_path, capsys):
    holdings = tmp_path / "holdings.yml"
    holdings.write_text("- {ticker: OK, weight: 0.05}\n")
    bad_ips = tmp_path / "bad.md"
    bad_ips.write_text("---\nversion: 2\n---\nbody\n")

    code = main(
        [
            "propose",
            "--ips", str(bad_ips),
            "--holdings", str(holdings),
            "--market", "us",
        ]
    )
    out = capsys.readouterr().out
    assert code == 2
    assert "version" in out


# --- holdings entry state (T3) ------------------------------------------------


def test_holdings_from_yaml_pre_t3_file_still_loads(tmp_path):
    """Old holdings.yml — no entry-state keys — parses unchanged."""
    f = tmp_path / "holdings.yml"
    f.write_text("- {ticker: AAPL, weight: 0.08, theme: tech, leverage: 2.0, verdict: buy}\n")
    assert _holdings_from_yaml(str(f)) == [
        Holding(ticker="AAPL", weight=0.08, theme="tech", leverage=2.0, verdict="buy")
    ]


def test_holdings_from_yaml_round_trips_entry_state(tmp_path):
    f = tmp_path / "holdings.yml"
    f.write_text(
        "- ticker: AAPL\n"
        "  weight: 0.08\n"
        "  entry_price: 180.5\n"
        "  entry_date: 2025-01-15\n"  # unquoted: PyYAML gives a datetime.date
        "  setup_type: value_dip\n"
        "  thesis: services margin re-rate\n"
        "  invalidation_price: 150.0\n"
    )
    (h,) = _holdings_from_yaml(str(f))
    assert (h.entry_price, h.entry_date, h.setup_type) == (180.5, "2025-01-15", "value_dip")
    assert (h.thesis, h.invalidation_price) == ("services margin re-rate", 150.0)


def test_holdings_from_yaml_unknown_key_names_the_key(tmp_path):
    f = tmp_path / "holdings.yml"
    f.write_text("- {ticker: AAPL, weight: 0.08, entrey_price: 180.5}\n")
    with pytest.raises(ValueError, match="entrey_price"):
        _holdings_from_yaml(str(f))


def test_holdings_from_yaml_rejects_unknown_setup_type(tmp_path):
    f = tmp_path / "holdings.yml"
    f.write_text("- {ticker: AAPL, weight: 0.08, setup_type: dip_buy}\n")
    with pytest.raises(ValueError, match="dip_buy"):
        _holdings_from_yaml(str(f))


def test_propose_exits_2_on_unknown_holdings_key(tmp_path, capsys):
    holdings = tmp_path / "holdings.yml"
    holdings.write_text("- {ticker: AAPL, weight: 0.08, entrey_price: 180.5}\n")
    code = main(
        [
            "propose",
            "--ips", str(EXAMPLES / "ips-balanced.md"),
            "--holdings", str(holdings),
            "--market", "us",
        ]
    )
    assert code == 2
    assert "entrey_price" in capsys.readouterr().err


# --- propose: screener wiring (T4) --------------------------------------------
#
# No network: a stub provider is injected by monkeypatching the lazily-imported
# `kuroshio.providers.get_provider` that cmd_propose resolves at call time.
N_TW = 65  # TW profile needs MA60 -> 60 sessions of clean history
# examples/ips-balanced.md turnover.hurdle + friction.tw_roundtrip_pct/100
HURDLE = 0.15 + 0.585 / 100

# 8 names, monotone ramps — a cross-section wide enough that every rank in the
# 0..1 grid is occupied by a name with visibly different factors.
_SPECS = {
    "1101": (50.0, 80.0),    # mild uptrend
    "1102": (50.0, 150.0),   # strongest name in the panel
    "1103": (120.0, 60.0),   # downtrend
    "1104": (150.0, 60.0),   # steeper downtrends -> the tail of the cross-section
    "1105": (200.0, 60.0),
    "1106": (250.0, 60.0),
    "1107": (300.0, 60.0),
    "1108": (350.0, 60.0),
}
# TW Stage-1 needs a >1.5x last-session volume spike, so this dict IS the gate list.
_VOL_SPIKE = {"1101": 1_800_000.0, "1102": 3_000_000.0}


def _ramp(lo: float, hi: float) -> list[float]:
    return [lo + (hi - lo) * i / (N_TW - 1) for i in range(N_TW)]


def _tw_panel(vol_spike: dict[str, float] | None = None, specs: dict | None = None) -> Panel:
    specs = _SPECS if specs is None else specs
    dates = [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2024-01-01", periods=N_TW)]
    close = pd.DataFrame({t: _ramp(*lohi) for t, lohi in specs.items()}, index=dates)
    volume = pd.DataFrame({t: [1_000_000.0] * N_TW for t in close.columns}, index=dates)
    for ticker, vol in (_VOL_SPIKE if vol_spike is None else vol_spike).items():
        volume.loc[dates[-1], ticker] = vol
    return Panel(close=close, volume=volume)


def _holdings_yaml(path: Path, tickers, tail: str = "") -> Path:
    path.write_text("".join(f'- {{ticker: "{t}", weight: 0.05{tail}}}\n' for t in tickers))
    return path


class _StubProvider:
    name = "stub"

    def __init__(self, panel: Panel):
        self.panel = panel
        self.calls: list[tuple] = []

    def fetch_panel(self, tickers, lookback_days, end=None):
        self.calls.append((list(tickers), lookback_days, end))
        return self.panel


def _use_stub(monkeypatch, panel: Panel | None = None) -> _StubProvider:
    stub = _StubProvider(_tw_panel() if panel is None else panel)
    monkeypatch.setattr("kuroshio.providers.get_provider", lambda name: stub)
    return stub


def test_propose_scores_score_less_holdings_via_provider(tmp_path, capsys, monkeypatch):
    """Acceptance: a score-less holdings.yml produces scored cards end-to-end — and the
    weakest incumbent's auto-filled score is a real interior percentile of the whole
    cross-section, not the 0.000 a holdings-only pool hands its own last name (R2)."""
    stub = _use_stub(monkeypatch)
    holdings = _holdings_yaml(tmp_path / "holdings.yml", [t for t in _SPECS if t != "1102"])
    candidates = tmp_path / "candidates.yml"
    candidates.write_text('- {ticker: "1102", final_score: 0.90, verdict: buy}\n')

    code = main(
        [
            "propose",
            "--ips", str(EXAMPLES / "ips-balanced.md"),
            "--holdings", str(holdings),
            "--candidates", str(candidates),
            "--market", "tw",
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "No current holding has a screener score" not in out
    assert "SWAP 1108 → 1102" in out
    assert "incumbent 1108's 0.119" in out
    assert set(stub.calls[0][0]) == set(_SPECS)


def test_score_missing_keeps_hand_written_scores_per_name():
    """Acceptance: hand-written scores still win; only the absent ones get filled."""
    profile = get_profile("tw")
    holdings = [Holding(ticker=t, weight=0.05) for t in _SPECS]
    holdings[0].score = 0.123  # hand-typed, must survive
    challengers, auto = _score_missing(holdings, [], profile, _tw_panel(), HURDLE)
    assert challengers == []
    assert "1101" not in auto  # hand-typed -> not disclosed as auto-filled
    assert holdings[0].score == 0.123
    assert all(h.score is not None for h in holdings[1:])


def test_score_missing_scores_one_ticker_identically_in_both_roles():
    """R1: incumbent and challenger scores come from ONE cross-section, so the same
    ticker in both roles is the same number — the scale the swap gate subtracts on."""
    profile = get_profile("tw")
    holdings = [Holding(ticker=t, weight=0.05) for t in _SPECS]
    challenger = Candidate(ticker="1101", date="2024-01-01", rank=0, final_score=None)
    kept, _ = _score_missing(holdings, [challenger], profile, _tw_panel(), HURDLE)
    incumbent = next(h.score for h in holdings if h.ticker == "1101")
    assert kept[0].final_score == incumbent
    assert 0.0 < incumbent < 1.0  # a real rank, not an artifact of a 2-name pool


@pytest.mark.parametrize("tickers", [["1103"], ["1101", "1103"]])
def test_propose_refuses_when_the_hurdle_cannot_reject_anything(
    tmp_path, capsys, monkeypatch, tickers
):
    """R2/R13: `final_score` moves in steps of `min_rank_weight / (n - 1)` — 0.333 at
    n=2, 0.167 at n=3 — both at or above the 0.156 hurdle+friction, so every non-tie
    ordering of that pool clears the hurdle by construction and the gate cannot reject
    anything. Nothing is auto-filled; the allocator's honest ALERT stands."""
    _use_stub(monkeypatch)
    holdings = _holdings_yaml(tmp_path / "holdings.yml", tickers)
    candidates = tmp_path / "candidates.yml"
    candidates.write_text('- {ticker: "1102", final_score: 0.90, verdict: buy}\n')

    code = main(
        [
            "propose",
            "--ips", str(EXAMPLES / "ips-balanced.md"),
            "--holdings", str(holdings),
            "--candidates", str(candidates),
            "--market", "tw",
        ]
    )
    cap = capsys.readouterr()
    assert code == 0
    assert "SWAP" not in cap.out
    assert "No current holding has a screener score" in cap.out
    assert "cross-section" in cap.err


@pytest.mark.parametrize(
    "tickers,pool_n",
    [(["1101", "1103", "1104"], 4), ([t for t in _SPECS if t != "1102"], 8)],
)
def test_propose_scores_and_discloses_at_or_above_the_pool_floor(
    tmp_path, capsys, monkeypatch, tickers, pool_n
):
    """R13 boundary: at n=4 the smallest achievable gap is 0.111, below the 0.156
    hurdle+friction, so the gate can reject and auto-filling is allowed again — and the
    card still discloses the pool the ranks came from (R10)."""
    _use_stub(monkeypatch)
    holdings = _holdings_yaml(tmp_path / "holdings.yml", tickers)
    candidates = tmp_path / "candidates.yml"
    candidates.write_text('- {ticker: "1102", verdict: buy}\n')

    code = main(
        [
            "propose",
            "--ips", str(EXAMPLES / "ips-balanced.md"),
            "--holdings", str(holdings),
            "--candidates", str(candidates),
            "--market", "tw",
        ]
    )
    cap = capsys.readouterr()
    assert code == 0
    assert "SWAP" in cap.out
    assert f"among the {pool_n} names in your own files" in cap.out
    assert "so this gap is a rank distance within that pool" in cap.out


def test_propose_marks_a_tight_dispersion_gap_as_a_rank_distance(tmp_path, capsys, monkeypatch):
    """R10: eight names whose closes are 0.007% apart still produce a 0.857 gap —
    indistinguishable factors, a policy-clearing number. No pool-size floor can fix
    that (the extremes are 0.000/1.000 regardless of dispersion), so the card
    discloses what the number is instead of implying it measures the factors."""
    tight = {t: (150.0, 150.0 + 0.01 * i) for i, t in enumerate(_SPECS, start=1)}
    _use_stub(monkeypatch, _tw_panel(vol_spike={"1108": 1_800_000.0}, specs=tight))
    holdings = _holdings_yaml(tmp_path / "holdings.yml", [t for t in tight if t != "1108"])
    candidates = tmp_path / "candidates.yml"
    candidates.write_text('- {ticker: "1108", verdict: buy}\n')

    code = main(
        [
            "propose",
            "--ips", str(EXAMPLES / "ips-balanced.md"),
            "--holdings", str(holdings),
            "--candidates", str(candidates),
            "--market", "tw",
        ]
    )
    cap = capsys.readouterr()
    assert code == 0
    assert "SWAP 1101 → 1108" in cap.out
    assert "a gap of 0.857" in cap.out
    assert "Auto-filled score(s): 1108, 1101" in cap.out
    assert "among the 8 names in your own files" in cap.out
    assert "so this gap is a rank distance within that pool" in cap.out  # both auto-filled


def test_propose_swaps_for_the_only_gate_passing_challenger(tmp_path, capsys, monkeypatch):
    """R3: a lone Stage-1 passer is ranked against the whole cross-section — pctranking
    it against itself returns 0.000 and drops a genuine breakout in silence."""
    _use_stub(monkeypatch, _tw_panel(vol_spike={"1102": 3_000_000.0}))
    holdings = _holdings_yaml(tmp_path / "holdings.yml", [t for t in _SPECS if t != "1102"])
    candidates = tmp_path / "candidates.yml"
    candidates.write_text('- {ticker: "1102", verdict: buy}\n')

    code = main(
        [
            "propose",
            "--ips", str(EXAMPLES / "ips-balanced.md"),
            "--holdings", str(holdings),
            "--candidates", str(candidates),
            "--market", "tw",
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "SWAP 1108 → 1102" in out
    assert "Challenger 1102 scores 1.000" in out


def test_propose_reports_candidates_the_gate_dropped(tmp_path, capsys, monkeypatch):
    """Candidates with no final_score are eligible only if they pass Stage-1 — and the
    ones the gate drops are named on stderr instead of vanishing (R5)."""
    _use_stub(monkeypatch)
    holdings = tmp_path / "holdings.yml"
    holdings.write_text(
        '- {ticker: "1101", weight: 0.05, score: 0.10}\n'
        + "".join(f'- {{ticker: "{t}", weight: 0.05, score: 0.50}}\n' for t in list(_SPECS)[3:])
    )
    candidates = tmp_path / "candidates.yml"
    candidates.write_text(
        '- {ticker: "1102", verdict: buy}\n'
        '- {ticker: "1103", verdict: buy}\n'  # downtrend -> Stage-1 rejects it
    )

    code = main(
        [
            "propose",
            "--ips", str(EXAMPLES / "ips-balanced.md"),
            "--holdings", str(holdings),
            "--candidates", str(candidates),
            "--market", "tw",
        ]
    )
    cap = capsys.readouterr()
    assert code == 0
    assert "SWAP 1101 → 1102" in cap.out
    assert "incumbent 1101's 0.100" in cap.out  # the hand-typed score, untouched
    # R14: one side hand-typed -> the gap is not a rank distance in any single scale.
    assert "Auto-filled score(s): 1102 —" in cap.out  # only the filled side is named
    assert "1101's score is hand-typed and not on that scale" in cap.out
    assert "subtracts two different scales" in cap.out
    assert "so this gap is a rank distance within that pool" not in cap.out
    assert "1103" not in cap.out
    assert "1103" in cap.err and "Stage-1" in cap.err


def test_propose_exits_2_on_unknown_candidates_key(tmp_path, capsys):
    """R4: `final_scores:` is a typo, not a request for a fetched score."""
    holdings = tmp_path / "holdings.yml"
    holdings.write_text('- {ticker: "1101", weight: 0.05, score: 0.40}\n')
    candidates = tmp_path / "candidates.yml"
    candidates.write_text('- {ticker: "1102", final_scores: 0.90, verdict: buy}\n')

    code = main(
        [
            "propose",
            "--ips", str(EXAMPLES / "ips-balanced.md"),
            "--holdings", str(holdings),
            "--candidates", str(candidates),
            "--market", "tw",
        ]
    )
    assert code == 2
    assert "final_scores" in capsys.readouterr().err


def test_propose_never_fetches_when_every_score_is_hand_written(tmp_path, capsys, monkeypatch):
    def _boom(name):
        raise AssertionError("propose must not touch a provider when all scores are present")

    monkeypatch.setattr("kuroshio.providers.get_provider", _boom)
    holdings = tmp_path / "holdings.yml"
    holdings.write_text('- {ticker: "1101", weight: 0.05, score: 0.40}\n')
    candidates = tmp_path / "candidates.yml"
    candidates.write_text('- {ticker: "1102", final_score: 0.90, verdict: buy}\n')

    code = main(
        [
            "propose",
            "--ips", str(EXAMPLES / "ips-balanced.md"),
            "--holdings", str(holdings),
            "--candidates", str(candidates),
            "--market", "tw",
        ]
    )
    assert code == 0
    assert "SWAP 1101 → 1102" in capsys.readouterr().out


def test_propose_exits_2_when_the_provider_is_not_installed(tmp_path, capsys, monkeypatch):
    def _missing(name):
        raise ImportError("no FinMind here")

    monkeypatch.setattr("kuroshio.providers.get_provider", _missing)
    holdings = tmp_path / "holdings.yml"
    holdings.write_text('- {ticker: "1101", weight: 0.05}\n')

    code = main(
        [
            "propose",
            "--ips", str(EXAMPLES / "ips-balanced.md"),
            "--holdings", str(holdings),
            "--market", "tw",
        ]
    )
    assert code == 2
    assert "not installed" in capsys.readouterr().err
