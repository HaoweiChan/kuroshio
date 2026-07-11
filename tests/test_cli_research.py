"""No-network, no-LLM tests for the `research` subcommand.

Stubs TradingAgentsGraph and the facet-cache functions at their import site
(module attributes) so `kuroshio.cli.cmd_research`'s lazy `from X import Y`
picks up the stub instead of ever touching langgraph/an LLM provider.
"""

from __future__ import annotations

import sys
from pathlib import Path

from kuroshio.cli import main

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

    instances: list["FakeGraph"] = []

    def __init__(self, selected_analysts=None, config=None):
        self.selected_analysts = selected_analysts
        self.config = config
        self.propagate_calls = []
        self.save_reports_calls = []
        FakeGraph.instances.append(self)

    def propagate(self, ticker, trade_date, seed_reports=None):
        self.propagate_calls.append({"ticker": ticker, "trade_date": trade_date, "seed_reports": seed_reports})
        return {"final_trade_decision": "stub"}, "Buy"

    def save_reports(self, final_state, ticker, save_path=None):
        self.save_reports_calls.append({"final_state": final_state, "ticker": ticker, "save_path": save_path})
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
