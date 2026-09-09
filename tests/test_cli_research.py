"""No-network, no-LLM tests for the `research` subcommand.

Stubs TradingAgentsGraph and the facet-cache functions at their import site
(module attributes) so `kuroshio.cli.cmd_research`'s lazy `from X import Y`
picks up the stub instead of ever touching langgraph/an LLM provider.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from kuroshio.cli import main

DECISION_MD_FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures" / "reports" / "AAA" / "2026-01-02" / "5_portfolio" / "decision.md"
).read_text()

FAKE_CONFIG = {
    "market_region": "us",
    "output_lang": "en",
    "facets_dir": "/unused/facets",
    "fundamentals_ttl_days": 7,
    "default_us_analysts": ["market", "social", "news", "fundamentals"],
    "default_tw_analysts": ["market", "chip", "social", "news", "fundamentals"],
}


class FakeGraph:
    """Stand-in for TradingAgentsGraph — records how it was constructed/called."""

    instances: list[FakeGraph] = []

    def __init__(self, selected_analysts=None, config=None):
        self.selected_analysts = selected_analysts
        self.config = config
        self.propagate_calls = []
        self.save_reports_calls = []
        FakeGraph.instances.append(self)

    def propagate(self, ticker, trade_date, seed_reports=None):
        self.propagate_calls.append(
            {"ticker": ticker, "trade_date": trade_date, "seed_reports": seed_reports}
        )
        return {"final_trade_decision": "stub"}, "Buy"

    def save_reports(self, final_state, ticker, save_path=None):
        self.save_reports_calls.append({"final_state": final_state, "ticker": ticker, "save_path": save_path})
        return Path(save_path) / "complete_report.md"


class FakeGraphWithDecision(FakeGraph):
    """Also writes 5_portfolio/decision.md, the way the vendored report writer does —
    needed to exercise TASK-18's decision.json sidecar without touching the real engine."""

    def propagate(self, ticker, trade_date, seed_reports=None):
        self.propagate_calls.append(
            {"ticker": ticker, "trade_date": trade_date, "seed_reports": seed_reports}
        )
        final_state = {
            "final_trade_decision": "stub",
            "strategy_payload": {"risk_controls": {"stop_loss": 90.0, "price_target": 130.0}},
        }
        return final_state, "Buy"

    def save_reports(self, final_state, ticker, save_path=None):
        self.save_reports_calls.append({"final_state": final_state, "ticker": ticker, "save_path": save_path})
        portfolio_dir = Path(save_path) / "5_portfolio"
        portfolio_dir.mkdir(parents=True, exist_ok=True)
        (portfolio_dir / "decision.md").write_text(DECISION_MD_FIXTURE, encoding="utf-8")
        return Path(save_path) / "complete_report.md"


def _stub_engine(monkeypatch, plan_facets=None, write_back=None):
    import kuroshio.agents.engine.default_config as default_config_mod
    import kuroshio.agents.engine.graph.facet_cache as facet_cache_mod
    import kuroshio.agents.engine.graph.trading_graph as trading_graph_mod

    FakeGraph.instances = []
    monkeypatch.setattr(default_config_mod, "DEFAULT_CONFIG", FAKE_CONFIG)
    monkeypatch.setattr(trading_graph_mod, "TradingAgentsGraph", FakeGraph)
    if plan_facets is not None:
        monkeypatch.setattr(facet_cache_mod, "plan_facets", plan_facets)
    if write_back is not None:
        monkeypatch.setattr(facet_cache_mod, "write_back", write_back)


# --- arg parsing / no-cache path ---------------------------------------------


def test_research_no_cache_skips_plan_facets(monkeypatch, tmp_path, capsys):
    def _boom(**kwargs):
        raise AssertionError("plan_facets must not be called with --no-cache")

    _stub_engine(monkeypatch, plan_facets=_boom)

    code = main([
        "research", "AAPL", "--market", "us", "--date", "2026-07-01",
        "--no-cache", "--out", str(tmp_path),
    ])
    out = capsys.readouterr().out

    assert code == 0
    graph = FakeGraph.instances[0]
    assert graph.selected_analysts == FAKE_CONFIG["default_us_analysts"]
    assert graph.propagate_calls[0]["seed_reports"] == {}
    assert graph.propagate_calls[0]["trade_date"] == "2026-07-01"
    assert "report:" in out
    assert "verdict: Buy" in out


# --- cache path ---------------------------------------------------------------


def test_research_cache_path_passes_seed_reports_through(monkeypatch, tmp_path):
    seed = {"sentiment_report": "cached sentiment content"}
    plan_calls = []
    write_back_calls = []

    def _fake_plan_facets(**kwargs):
        plan_calls.append(kwargs)
        return ["market"], seed

    def _fake_write_back(**kwargs):
        write_back_calls.append(kwargs)

    _stub_engine(monkeypatch, plan_facets=_fake_plan_facets, write_back=_fake_write_back)

    code = main(["research", "AAPL", "--out", str(tmp_path)])

    assert code == 0
    assert plan_calls[0]["ticker"] == "AAPL"
    assert plan_calls[0]["available_facets"] == FAKE_CONFIG["default_us_analysts"]
    graph = FakeGraph.instances[0]
    assert graph.selected_analysts == ["market"]
    assert graph.propagate_calls[0]["seed_reports"] == seed
    assert write_back_calls[0]["regenerated_facets"] == ["market"]
    assert graph.save_reports_calls[0]["save_path"] == Path(tmp_path) / "AAPL" / plan_calls[0]["trade_date"]


# --- missing optional dependency ---------------------------------------------


def test_research_missing_agents_extra_exits_2(monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "kuroshio.agents.engine.default_config", None)

    code = main(["research", "AAPL"])
    err = capsys.readouterr().err

    assert code == 2
    assert 'pip install "kuroshio[agents]"' in err


# --- custom analysts selection -------------------------------------------------


def test_research_custom_analysts_and_lang(monkeypatch, tmp_path):
    def _fake_plan_facets(**kwargs):
        return list(kwargs["available_facets"]), {}

    _stub_engine(monkeypatch, plan_facets=_fake_plan_facets, write_back=lambda **kw: None)

    code = main([
        "research", "2330.TW", "--market", "tw", "--lang", "zh-TW",
        "--analysts", "market,chip", "--out", str(tmp_path),
    ])

    assert code == 0
    graph = FakeGraph.instances[0]
    assert graph.selected_analysts == ["market", "chip"]
    assert graph.config["output_lang"] == "zh-TW"
    assert graph.config["market_region"] == "tw"


# --- ledger wiring (T6) --------------------------------------------------------


def test_research_appends_a_rating_row_to_the_ledger(monkeypatch, tmp_path, capsys):
    from kuroshio.core import ledger

    monkeypatch.setenv("KUROSHIO_LEDGER_DIR", str(tmp_path / "ledger"))
    _stub_engine(monkeypatch)

    code = main([
        "research", "AAPL", "--market", "us", "--date", "2026-07-01",
        "--no-cache", "--out", str(tmp_path),
    ])
    capsys.readouterr()

    assert code == 0
    rows = ledger.load(ledger.ledger_dir() / ledger.RATINGS)
    assert rows == [{
        "date": "2026-07-01", "market": "us", "ticker": "AAPL",
        "rating": "Buy", "stop_loss": None, "price_target": None, "close": None,
    }]


# --- decision.json sidecar (TASK-18) --------------------------------------------

_EXPECTED_DECISION_JSON = {
    "ticker": "AAA", "date": "2026-01-02", "market": "us", "rating": "Buy",
    "stop_loss": 90.0, "price_target": 130.0, "close": None,
    "executive_summary": (
        "Half a position at the close, the rest above 108 on volume; stop 90, target "
        "130, horizon two quarters. Synthetic text, no real security."
    ),
    "investment_thesis": (
        "Growth is real and the ranking found it before the tape did. The bear case "
        "is a valuation opinion with no fact pattern behind it."
    ),
    "source": None, "model": None,
}


def test_research_writes_decision_json_beside_decision_md(monkeypatch, tmp_path, capsys):
    import kuroshio.agents.engine.graph.trading_graph as trading_graph_mod

    _stub_engine(monkeypatch)
    monkeypatch.setattr(trading_graph_mod, "TradingAgentsGraph", FakeGraphWithDecision)

    code = main([
        "research", "AAA", "--market", "us", "--date", "2026-01-02",
        "--no-cache", "--out", str(tmp_path),
    ])
    capsys.readouterr()

    assert code == 0
    path = tmp_path / "AAA" / "2026-01-02" / "5_portfolio" / "decision.json"
    assert json.loads(path.read_text()) == _EXPECTED_DECISION_JSON


def test_research_writes_decision_json_even_with_no_ledger(monkeypatch, tmp_path, capsys):
    import kuroshio.agents.engine.graph.trading_graph as trading_graph_mod

    _stub_engine(monkeypatch)
    monkeypatch.setattr(trading_graph_mod, "TradingAgentsGraph", FakeGraphWithDecision)

    code = main([
        "research", "AAA", "--market", "us", "--date", "2026-01-02",
        "--no-cache", "--out", str(tmp_path), "--no-ledger",
    ])
    capsys.readouterr()

    assert code == 0
    path = tmp_path / "AAA" / "2026-01-02" / "5_portfolio" / "decision.json"
    assert json.loads(path.read_text()) == _EXPECTED_DECISION_JSON
