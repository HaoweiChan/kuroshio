"""No-network tests for kuroshio.cli — arg parsing, YAML helpers, and the
propose/ips-validate commands end-to-end via main(). `screen` is only
exercised for its argument-error path here; the network path is untested
by design (no network in this repo's test suite)."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

from kuroshio.cli import (
    _candidates_from_yaml,
    _holdings_from_yaml,
    _load_universe,
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


def test_propose_emits_trim_card_for_hard_cap_breach(tmp_path, capsys, monkeypatch):
    # ips-balanced.md sets caps.book_vol_target_pct, so propose now fetches a panel even
    # though every score here is hand-typed — stub the provider rather than hit the network.
    _use_stub(monkeypatch)
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


def test_propose_no_candidates_still_runs(tmp_path, capsys, monkeypatch):
    _use_stub(monkeypatch)  # ips-balanced.md's book_vol_target_pct needs a panel fetch
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


def test_propose_with_candidates_swap(tmp_path, capsys, monkeypatch):
    _use_stub(monkeypatch)  # ips-balanced.md's book_vol_target_pct needs a panel fetch
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
# Claims the refusal notice must not make. Each was shipped in a previous round and each
# was false in the configuration it was not derived on (R13 -> R17 -> R19): the floor is a
# conservative heuristic off one factor weight, not a theorem about the score's step size.
_STEP_GRID_CLAIMS = (
    "clears it by construction",
    "before two scores can differ",
    "cannot differ by less than",
    "can reject nothing",
    "the hurdle cannot reject",
)

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


def _tw_panel(
    vol_spike: dict[str, float] | None = None,
    specs: dict | None = None,
    institutional: bool = False,
) -> Panel:
    specs = _SPECS if specs is None else specs
    dates = [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2024-01-01", periods=N_TW)]
    close = pd.DataFrame({t: _ramp(*lohi) for t, lohi in specs.items()}, index=dates)
    volume = pd.DataFrame({t: [1_000_000.0] * N_TW for t in close.columns}, index=dates)
    for ticker, vol in (_VOL_SPIKE if vol_spike is None else vol_spike).items():
        volume.loc[dates[-1], ticker] = vol
    # institutional=True is the config FinMind actually returns; None (the default) is the
    # degraded one MIN_RANK_WEIGHT is derived from. See R17.
    insti = None
    if institutional:
        insti = pd.DataFrame(
            {t: [50_000.0 * (i + 1)] * N_TW for i, t in enumerate(close.columns)}, index=dates
        )
    return Panel(close=close, volume=volume, institutional=insti)


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


def test_propose_refusal_notice_claims_a_heuristic_not_a_theorem(tmp_path, capsys, monkeypatch):
    """R17/R19: `need` is read off one factor weight, so it over-refuses — with TW
    institutional flow present (what FinMind actually returns) the weights are finer than
    MIN_RANK_WEIGHT assumes and a 3-name pool could well have been rankable. The guard
    still refuses, which costs the user only a manual `kuroshio screen`. What it must not
    do is dress that floor up as arithmetic about where the composite's steps land."""
    panel = _tw_panel(institutional=True)
    profile = get_profile("tw")
    scored = profile.score_names(panel, tickers=list(_SPECS))
    assert "institution" in scored[0].scores  # the non-degraded path is really exercised

    _use_stub(monkeypatch, panel)
    holdings = _holdings_yaml(tmp_path / "holdings.yml", ["1101", "1103"])
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
    assert "No current holding has a screener score" in cap.out
    assert "deliberately conservative floor" in cap.err
    assert "may well be refusing a pool your hurdle could have judged" in cap.err
    assert not [c for c in _STEP_GRID_CLAIMS if c in cap.err]


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


# --- propose: the US-leadership half of the same guard (R18) -------------------
#
# Every other `--market us-leadership` propose test hand-types `score:`, so
# `_score_missing` is never reached on that path; without these, `us.MIN_RANK_WEIGHT`
# is pinned by nothing.
N_US = 210  # us-leadership profile needs MA200 -> 200 sessions of clean history
_US_SPECS = {"AAA": (100.0, 110.0), "BBB": (100.0, 130.0), "DDD": (100.0, 145.0),
             "CCC": (100.0, 160.0), "SPY": (100.0, 101.0)}  # SPY = the profile's benchmark


def _us_panel() -> Panel:
    dates = [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2023-01-02", periods=N_US)]
    ramp = lambda lo, hi: [lo + (hi - lo) * i / (N_US - 1) for i in range(N_US)]  # noqa: E731
    close = pd.DataFrame({t: ramp(*lohi) for t, lohi in _US_SPECS.items()}, index=dates)
    # 1e6 shares x ~$100 clears the profile's $25M/day liquidity floor.
    volume = pd.DataFrame({t: [1_000_000.0] * N_US for t in close.columns}, index=dates)
    return Panel(close=close, volume=volume)


@pytest.mark.parametrize("tickers", [["AAA", "BBB"], ["AAA", "BBB", "DDD"]])
def test_propose_guards_the_us_leadership_pool_too(tmp_path, capsys, monkeypatch, tickers):
    """R18: the same `min_rank_weight / (n - 1)` guard, read off the us-leadership
    profile's own weights — a 3-name pool refuses, a 4-name pool scores and discloses."""
    _use_stub(monkeypatch, _us_panel())
    holdings = _holdings_yaml(tmp_path / "holdings.yml", tickers)
    candidates = tmp_path / "candidates.yml"
    candidates.write_text('- {ticker: "CCC", verdict: buy}\n')

    code = main(
        [
            "propose",
            "--ips", str(EXAMPLES / "ips-balanced.md"),
            "--holdings", str(holdings),
            "--candidates", str(candidates),
            "--market", "us-leadership",
        ]
    )
    cap = capsys.readouterr()
    assert code == 0
    if len(tickers) == 2:  # pool of 3 -> below the us-leadership floor of 4
        assert "SWAP" not in cap.out
        assert "No current holding has a screener score" in cap.out
        # R19: the step-grid claim is false for US — its degraded weights (0.625, 0.375)
        # are not commensurate, so the composite does not move on a min_rank_weight grid.
        assert "deliberately conservative floor" in cap.err
        assert not [c for c in _STEP_GRID_CLAIMS if c in cap.err]
    else:                  # pool of 4 -> scores, and says what the number is
        assert "SWAP AAA → CCC" in cap.out
        assert "among the 4 names in your own files" in cap.out
        assert "so this gap is a rank distance within that pool" in cap.out


# --- propose: the US 12-1 momentum guard (`us`, min_rank_weight=1.0) -----------
#
# min_rank_weight=1.0 (single pctrank IS the score) with the balanced IPS's
# turnover hurdle (0.15 + us_roundtrip_pct/100 = 0.1502) gives
# need = floor(1.0 / 0.1502) + 2 == 8.
N_US_MOM = 260  # us profile's min_history: 252-session momentum lookback + skip headroom
_US_MOM_SPECS = {
    "AAA": (100.0, 105.0), "BBB": (100.0, 115.0), "CCC": (100.0, 125.0),
    "DDD": (100.0, 135.0), "EEE": (100.0, 145.0), "FFF": (100.0, 155.0),
    "GGG": (100.0, 165.0), "SPY": (100.0, 101.0),  # SPY = the profile's benchmark
}


def _us_mom_panel() -> Panel:
    dates = [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2023-01-02", periods=N_US_MOM)]
    ramp = lambda lo, hi: [lo + (hi - lo) * i / (N_US_MOM - 1) for i in range(N_US_MOM)]  # noqa: E731
    close = pd.DataFrame({t: ramp(*lohi) for t, lohi in _US_MOM_SPECS.items()}, index=dates)
    volume = pd.DataFrame({t: [1_000_000.0] * N_US_MOM for t in close.columns}, index=dates)
    return Panel(close=close, volume=volume)


def test_propose_guards_the_us_momentum_pool_too(tmp_path, capsys, monkeypatch):
    """The `us` profile's guard needs 8 names (see module comment above); a 7-name
    pool is one short and refuses, mirroring the us-leadership case above."""
    _use_stub(monkeypatch, _us_mom_panel())
    tickers = [t for t in _US_MOM_SPECS if t not in ("SPY", "GGG")]  # 6 names
    holdings = _holdings_yaml(tmp_path / "holdings.yml", tickers)
    candidates = tmp_path / "candidates.yml"
    candidates.write_text('- {ticker: "GGG", verdict: buy}\n')  # 7th name -> still below 8

    code = main(
        [
            "propose",
            "--ips", str(EXAMPLES / "ips-balanced.md"),
            "--holdings", str(holdings),
            "--candidates", str(candidates),
            "--market", "us",
        ]
    )
    cap = capsys.readouterr()
    assert code == 0
    assert "SWAP" not in cap.out
    assert "No current holding has a screener score" in cap.out
    assert "deliberately conservative floor" in cap.err
    assert not [c for c in _STEP_GRID_CLAIMS if c in cap.err]


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

    # ips-aggressive.md leaves caps.book_vol_target_pct unset — ips-balanced.md sets it,
    # which needs a panel for book_vol even when every score is hand-written, and would
    # make this test's premise (no fetch reason at all) false rather than exercising it.
    code = main(
        [
            "propose",
            "--ips", str(EXAMPLES / "ips-aggressive.md"),
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


# --- propose: thesis monitoring wiring (T5) -----------------------------------


def test_propose_fetches_for_monitoring_and_dispatches_on_setup_type(
    tmp_path, capsys, monkeypatch
):
    """Acceptance, end to end: every score is hand-typed, so the only reason to touch a
    provider is monitoring. 1103 and 1104 both close far under their MA50 (the _SPECS
    ramps are downtrends); only the trend_add is alerted on that, the value_dip on its
    own invalidation price, and the third value_dip — same tape, level not breached —
    produces nothing."""
    stub = _use_stub(monkeypatch)
    holdings = tmp_path / "holdings.yml"
    holdings.write_text(
        '- {ticker: "1103", weight: 0.05, score: 0.5, setup_type: trend_add, entry_price: 100.0}\n'
        '- {ticker: "1104", weight: 0.05, score: 0.5, setup_type: value_dip,'
        ' entry_price: 80.0, invalidation_price: 65.0}\n'
        '- {ticker: "1105", weight: 0.05, score: 0.5, setup_type: value_dip,'
        ' entry_price: 70.0, invalidation_price: 50.0}\n'
    )

    code = main(
        [
            "propose",
            "--ips", str(EXAMPLES / "ips-balanced.md"),
            "--holdings", str(holdings),
            "--market", "tw",
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert stub.calls, "monitoring needs prices — propose must fetch for setup_type holdings"
    assert "1103 was opened as a trend_add and the trend has broken" in out
    assert "1104 was opened as a value_dip and its invalidation price is breached" in out
    assert "1105" not in out
    # R6/R9: the session the panel was read from reaches the card, named and nothing
    # more — the run has no market calendar to say whether it is open or closed.
    last_session = _tw_panel().close.index[-1]
    assert f"at 60.00 ({last_session} session)" in out
    assert "closed at" not in out and "still-open" not in out


# --- propose: max adverse excursion wiring (T6) --------------------------------


def test_propose_fetches_prices_for_an_entry_price_with_no_setup_type(
    tmp_path, capsys, monkeypatch
):
    """The MAE rule reads no setup_type, so the fetch gate cannot key off one either: a
    holdings file whose scores are all hand-typed and whose positions carry only an
    entry_price still needs this session's price, or the card can never fire."""
    stub = _use_stub(monkeypatch)
    holdings = tmp_path / "holdings.yml"
    holdings.write_text('- {ticker: "1103", weight: 0.05, score: 0.5, entry_price: 100.0}\n')

    code = main(
        [
            "propose",
            "--ips", str(EXAMPLES / "ips-balanced.md"),
            "--holdings", str(holdings),
            "--market", "tw",
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert stub.calls, "the loss-from-entry rule needs prices — propose must fetch for entry_price"
    assert "### DECIDE 1103" in out
    assert "-40.0% from your entry price of 100.00" in out
    assert "per your IPS: caps.max_adverse_excursion_pct" in out


# --- propose: book vol target wiring (TASK-9) -----------------------------------


def _volatile_panel(ticker: str = "VOL", n: int = 65) -> Panel:
    """One name, alternating +5%/-5% daily — its trailing-20-session annualized vol is
    far above any realistic IPS target, so a book that's all this one name needs a
    SCALE card at a 15% target."""
    dates = [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2024-01-01", periods=n)]
    prices = [100.0]
    for i in range(1, n):
        prices.append(prices[-1] * (1.05 if i % 2 == 0 else 0.95))
    close = pd.DataFrame({ticker: prices}, index=dates)
    volume = pd.DataFrame({ticker: [1_000_000.0] * n}, index=dates)
    return Panel(close=close, volume=volume, institutional=None)


def test_propose_emits_a_scale_card_when_the_book_is_volatile(tmp_path, capsys, monkeypatch):
    """A set caps.book_vol_target_pct needs a panel even when every score is hand-typed
    and no position is monitored — the fetch-gate case T5/T6 above don't cover, since
    neither `need_scores` nor `monitored` is true here. No example IPS sets the field
    (it is opt-in), so the test writes one."""
    stub = _use_stub(monkeypatch, _volatile_panel())
    holdings = tmp_path / "holdings.yml"
    holdings.write_text('- {ticker: "VOL", weight: 0.05, score: 0.5}\n')
    ips = tmp_path / "ips.md"
    ips.write_text(
        (EXAMPLES / "ips-balanced.md").read_text().replace(
            "  exemptions: []", "  book_vol_target_pct: 15\n  exemptions: []", 1
        )
    )

    code = main(
        [
            "propose",
            "--ips", str(ips),
            "--holdings", str(holdings),
            "--market", "us",
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert stub.calls, "book_vol_target_pct needs a panel even with no other fetch reason"
    assert "### SCALE gross exposure" in out
    assert "15.0" in out  # the target it read
    assert "20" in out  # the trailing window


# --- screen / evaluate: ledger wiring (T6) --------------------------------------


class _FundamentalsStub(_StubProvider):
    """fetch_fundamentals returns a snapshot for GGG only, None for everything else —
    exercises the "missing fundamentals leaves the row's snapshot null" path."""

    def fetch_fundamentals(self, ticker):
        if ticker != "GGG":
            return None
        return {
            "forward_pe": 15.0, "forward_eps": 2.0, "trailing_eps": 1.8, "trailing_pe": 16.0,
            "market_cap": 1_000_000_000.0, "sector": "Technology", "industry": "Software",
            "eps_rev_up_30d": 8, "eps_rev_down_30d": 2,
        }


def test_screen_appends_score_rows_with_a_fundamentals_snapshot(tmp_path, capsys, monkeypatch):
    from kuroshio.core import ledger

    monkeypatch.setenv("KUROSHIO_LEDGER_DIR", str(tmp_path / "ledger"))
    stub = _FundamentalsStub(_us_mom_panel())
    monkeypatch.setattr("kuroshio.providers.get_provider", lambda name: stub)

    code = main(["screen", "--market", "us", "--tickers", ",".join(_US_MOM_SPECS)])
    cap = capsys.readouterr()
    assert code == 0
    assert "ledger:" in cap.err

    n_candidates = int(cap.out.splitlines()[0].split("candidates=")[1])
    rows = ledger.load(ledger.ledger_dir() / ledger.SCORES)
    assert len(rows) == n_candidates > 0

    ggg = next(r for r in rows if r["ticker"] == "GGG")
    assert ggg["fundamentals"]["forward_pe"] == 15.0
    assert ggg["fundamentals"]["eps_rev_up_30d"] == 8
    others = [r for r in rows if r["ticker"] != "GGG"]
    assert others and all(r["fundamentals"] is None for r in others)


def test_screen_no_ledger_writes_nothing(tmp_path, capsys, monkeypatch):
    from kuroshio.core import ledger

    ledger_dir = tmp_path / "ledger"
    monkeypatch.setenv("KUROSHIO_LEDGER_DIR", str(ledger_dir))
    _use_stub(monkeypatch, _us_mom_panel())

    code = main(["screen", "--market", "us", "--tickers", ",".join(_US_MOM_SPECS), "--no-ledger"])
    assert code == 0
    assert not (ledger_dir / ledger.SCORES).exists()


def _us_mom_panel_n(n: int) -> Panel:
    """Same shape as `_us_mom_panel` but with enough sessions for a screen `asof` past
    the 252-session momentum lookback to also have `--horizon`-worth of forward data
    for `evaluate` — 260 rows (the min_history fixture) has no room for both."""
    dates = [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2023-01-02", periods=n)]
    ramp = lambda lo, hi: [lo + (hi - lo) * i / (n - 1) for i in range(n)]  # noqa: E731
    close = pd.DataFrame({t: ramp(*lohi) for t, lohi in _US_MOM_SPECS.items()}, index=dates)
    volume = pd.DataFrame({t: [1_000_000.0] * n for t in close.columns}, index=dates)
    return Panel(close=close, volume=volume)


def test_evaluate_prints_rank_ic_after_two_screen_runs(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("KUROSHIO_LEDGER_DIR", str(tmp_path / "ledger"))
    panel = _us_mom_panel_n(300)
    _use_stub(monkeypatch, panel)

    for asof in (panel.close.index[255], panel.close.index[260]):
        assert main(["screen", "--market", "us", "--tickers", ",".join(_US_MOM_SPECS), "--asof", asof]) == 0
    capsys.readouterr()

    code = main(["evaluate", "--market", "us", "--horizon", "20", "--top", "3"])
    out = capsys.readouterr().out
    assert code == 0
    assert "rank-IC" in out
    assert "top-k" in out


def test_evaluate_with_one_run_reports_need_at_least_two_dates(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("KUROSHIO_LEDGER_DIR", str(tmp_path / "ledger"))
    panel = _us_mom_panel_n(300)
    _use_stub(monkeypatch, panel)
    main(["screen", "--market", "us", "--tickers", ",".join(_US_MOM_SPECS), "--asof", panel.close.index[255]])
    capsys.readouterr()

    code = main(["evaluate", "--market", "us"])
    out = capsys.readouterr().out
    assert code == 0
    assert "need at least 2" in out


# --- propose: `--universe-file` gives the hurdle a cross-section (TASK-7) -------
#
# 60 names, each with a distinct constant per-session growth rate, so the panel's
# 12-1 momentum scores are strictly ordered by ticker index and the challenger's
# pctrank position is known exactly — see the derivation in the acceptance test below.

N_UNIVERSE = 260  # same session floor as `_us_mom_panel` — the `us` profile's min_history
_UNIVERSE_TICKERS = [f"U{i:02d}" for i in range(60)]
HURDLE_US = 0.15 + 0.02 / 100  # balanced IPS: turnover.hurdle + us_roundtrip_pct / 100


def _us_universe_panel() -> Panel:
    dates = [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2023-01-02", periods=N_UNIVERSE)]
    close = pd.DataFrame(
        {
            t: [100.0 * (1.0002 + 0.00002 * i) ** day for day in range(N_UNIVERSE)]
            for i, t in enumerate(_UNIVERSE_TICKERS)
        },
        index=dates,
    )
    close["SPY"] = [100.0] * N_UNIVERSE  # flat benchmark
    volume = pd.DataFrame({t: [1_000_000.0] * N_UNIVERSE for t in close.columns}, index=dates)
    return Panel(close=close, volume=volume)


def test_score_missing_with_universe_ranks_the_challenger_against_the_index():
    """A universe adds a third source of names to the ranking pool (holdings ∪
    challengers ∪ universe) instead of just the user's own files, so an auto-filled
    score is the challenger's exact pctrank position among all 60: U55 has the 56th
    (0-indexed 55th) lowest growth rate of 60, so its score is 55 / (60 - 1)."""
    panel = _us_universe_panel()
    profile = get_profile("us")
    holdings = [Holding(ticker=t, weight=0.05) for t in ("U05", "U25", "U45")]
    challenger = Candidate(ticker="U55", date="2024-01-01", rank=0, final_score=None)

    kept, auto = _score_missing(
        holdings, [challenger], profile, panel, HURDLE_US, universe=_UNIVERSE_TICKERS
    )

    assert auto["U55"] == 60  # ranked against the whole universe, not a 4-name pool
    assert kept[0].final_score == pytest.approx(55 / 59)


def test_propose_universe_file_names_the_pool_and_skips_the_small_pool_refusal(
    tmp_path, capsys, monkeypatch
):
    """Acceptance: with a 60-name universe file, `propose --market us` auto-fills the
    candidate's score against the whole universe (not just the 4 names in holdings +
    candidates — well under the `need=8` floor on their own), the SWAP card names the
    universe file instead of "your own files", and the small-pool refusal never fires."""
    _use_stub(monkeypatch, _us_universe_panel())
    holdings = _holdings_yaml(tmp_path / "holdings.yml", ("U05", "U25", "U45"))
    candidates = tmp_path / "candidates.yml"
    candidates.write_text('- {ticker: "U55", verdict: buy}\n')
    universe = tmp_path / "universe.txt"
    universe.write_text("\n".join(_UNIVERSE_TICKERS) + "\n")

    code = main(
        [
            "propose",
            "--ips", str(EXAMPLES / "ips-balanced.md"),
            "--holdings", str(holdings),
            "--candidates", str(candidates),
            "--market", "us",
            "--universe-file", str(universe),
        ]
    )
    cap = capsys.readouterr()
    assert code == 0
    assert "SWAP U05 → U55" in cap.out
    assert "the 60 names in the universe in universe.txt" in cap.out
    assert "too small a cross-section" not in cap.err


def test_propose_universe_file_accepts_a_members_snapshot_and_uses_the_last_row(
    tmp_path, capsys, monkeypatch
):
    """Acceptance: a `date,tickers` snapshot file (the `scripts/sp500_members.py`
    format) is accepted too, and the pool is the LAST row's tickers — an earlier,
    unrelated row must be ignored."""
    _use_stub(monkeypatch, _us_universe_panel())
    holdings = _holdings_yaml(tmp_path / "holdings.yml", ("U05", "U25", "U45"))
    candidates = tmp_path / "candidates.yml"
    candidates.write_text('- {ticker: "U55", verdict: buy}\n')
    universe = tmp_path / "members.csv"
    universe.write_text(
        "date,tickers\n"
        "2020-01-01,ZZZ\n"  # stale snapshot — must not be the pool used
        f"2024-01-01,{' '.join(_UNIVERSE_TICKERS)}\n"
    )

    code = main(
        [
            "propose",
            "--ips", str(EXAMPLES / "ips-balanced.md"),
            "--holdings", str(holdings),
            "--candidates", str(candidates),
            "--market", "us",
            "--universe-file", str(universe),
        ]
    )
    cap = capsys.readouterr()
    assert code == 0
    assert "SWAP U05 → U55" in cap.out
    assert "the 60 names in the universe in members.csv" in cap.out
    assert "too small a cross-section" not in cap.err


def test_propose_empty_universe_file_exits_2(tmp_path, capsys):
    holdings = _holdings_yaml(tmp_path / "holdings.yml", ["AAPL"], ", score: 0.5")
    universe = tmp_path / "universe.txt"
    universe.write_text("")

    code = main(
        [
            "propose",
            "--ips", str(EXAMPLES / "ips-balanced.md"),
            "--holdings", str(holdings),
            "--market", "us",
            "--universe-file", str(universe),
        ]
    )
    assert code == 2
    assert "error:" in capsys.readouterr().err


def test_load_universe_rejects_empty_file(tmp_path):
    f = tmp_path / "empty.txt"
    f.write_text("")
    with pytest.raises(ValueError):
        _load_universe(str(f))


def test_load_universe_missing_file_is_a_value_error(tmp_path):
    with pytest.raises(ValueError):
        _load_universe(str(tmp_path / "nope.txt"))


# --- mcp (TASK-10) -----------------------------------------------------------


def test_mcp_help_parses(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["mcp", "--help"])
    assert exc.value.code == 0
    assert "mcp" in capsys.readouterr().out


def test_mcp_missing_extra_exits_2(monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "kuroshio.mcp_server", None)

    code = main(["mcp"])
    err = capsys.readouterr().err

    assert code == 2
    assert 'pip install "kuroshio[mcp]"' in err
