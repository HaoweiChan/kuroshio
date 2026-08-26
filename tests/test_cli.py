"""No-network tests for kuroshio.cli — arg parsing, YAML helpers, and the
propose/ips-validate commands end-to-end via main(). `screen` is only
exercised for its argument-error path here; the network path is untested
by design (no network in this repo's test suite)."""

from __future__ import annotations

from pathlib import Path

import pytest

from kuroshio.cli import _candidates_from_yaml, _holdings_from_yaml, _parse_tickers, main
from kuroshio.types import Candidate, Holding

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
