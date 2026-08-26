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


def _ramp(lo: float, hi: float) -> list[float]:
    return [lo + (hi - lo) * i / (N_TW - 1) for i in range(N_TW)]


def _tw_panel() -> Panel:
    """1102 = strongest breakout, 1101 = mild uptrend, 1103 = downtrend (fails Stage-1)."""
    dates = [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2024-01-01", periods=N_TW)]
    close = pd.DataFrame(
        {"1101": _ramp(50.0, 80.0), "1102": _ramp(50.0, 150.0), "1103": _ramp(120.0, 60.0)},
        index=dates,
    )
    volume = pd.DataFrame({t: [1_000_000.0] * N_TW for t in close.columns}, index=dates)
    volume.loc[dates[-1], "1101"] = 1_800_000.0   # 1.8x baseline -> clears VOL_MULT_MIN
    volume.loc[dates[-1], "1102"] = 3_000_000.0   # 3x baseline
    return Panel(close=close, volume=volume)


class _StubProvider:
    name = "stub"

    def __init__(self, panel: Panel):
        self.panel = panel
        self.calls: list[tuple] = []

    def fetch_panel(self, tickers, lookback_days, end=None):
        self.calls.append((list(tickers), lookback_days, end))
        return self.panel


def _use_stub(monkeypatch) -> _StubProvider:
    stub = _StubProvider(_tw_panel())
    monkeypatch.setattr("kuroshio.providers.get_provider", lambda name: stub)
    return stub


def test_propose_scores_score_less_holdings_via_provider(tmp_path, capsys, monkeypatch):
    """Acceptance: a score-less holdings.yml produces scored cards end-to-end."""
    stub = _use_stub(monkeypatch)
    holdings = tmp_path / "holdings.yml"
    holdings.write_text('- {ticker: "1101", weight: 0.05}\n- {ticker: "1103", weight: 0.05}\n')
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
    assert "SWAP 1103 → 1102" in out
    assert set(stub.calls[0][0]) == {"1101", "1102", "1103"}


def test_score_missing_keeps_hand_written_scores_per_name():
    """Acceptance: hand-written scores still win; only the absent ones get filled."""
    profile = get_profile("tw")
    holdings = [
        Holding(ticker="1101", weight=0.05, score=0.123),  # hand-typed, must survive
        Holding(ticker="1103", weight=0.05),               # absent -> screener fills it
    ]
    challengers = _score_missing(holdings, [], profile, _tw_panel())
    assert challengers == []
    assert holdings[0].score == 0.123
    assert holdings[1].score is not None


def test_propose_scores_candidates_through_the_gated_screener(tmp_path, capsys, monkeypatch):
    """Candidates with no final_score go through the GATED screen — a name that
    fails Stage-1 gets no score and is therefore not a challenger."""
    _use_stub(monkeypatch)
    holdings = tmp_path / "holdings.yml"
    holdings.write_text('- {ticker: "1101", weight: 0.05, score: 0.10}\n')
    candidates = tmp_path / "candidates.yml"
    candidates.write_text(
        '- {ticker: "1102", verdict: buy}\n'
        '- {ticker: "1103", verdict: buy}\n'  # downtrend -> Stage-1 rejects, dropped
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
    out = capsys.readouterr().out
    assert code == 0
    assert "SWAP 1101 → 1102" in out
    assert "1103" not in out
    assert "incumbent 1101's 0.100" in out  # the hand-typed score, untouched


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
