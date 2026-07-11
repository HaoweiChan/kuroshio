"""Unit test for the constructor-injected portfolio_state_provider duck type
added while componentizing graph/trading_graph.py (replaces the excluded
private broker integration). Exercises _load_portfolio_snapshot /
_empty_portfolio_snapshot directly, bypassing __init__ (which needs LLM
provider config) since these two methods only touch self.market_region and
self.portfolio_state_provider.
"""

from kuroshio.agents.engine.graph.trading_graph import TradingAgentsGraph
from kuroshio.agents.engine.portfolio.state import PortfolioSnapshot


def _bare_graph(market_region: str, provider=None) -> TradingAgentsGraph:
    graph = object.__new__(TradingAgentsGraph)
    graph.market_region = market_region
    graph.portfolio_state_provider = provider
    return graph


def test_no_provider_returns_empty_snapshot():
    graph = _bare_graph("tw")
    snapshot = graph._load_portfolio_snapshot("2026-07-12")
    assert snapshot.market == "tw"
    assert snapshot.currency == "TWD"
    assert snapshot.nav is None
    assert snapshot.accounts == []


def test_us_empty_snapshot_uses_usd():
    graph = _bare_graph("us")
    snapshot = graph._empty_portfolio_snapshot()
    assert snapshot.currency == "USD"


def test_provider_returning_none_falls_back_to_empty():
    class _NullProvider:
        def load(self):
            return None

    graph = _bare_graph("tw", provider=_NullProvider())
    snapshot = graph._load_portfolio_snapshot("2026-07-12")
    assert snapshot.nav is None
    assert snapshot.accounts == []


def test_provider_snapshot_is_passed_through():
    live = PortfolioSnapshot(market="tw", currency="TWD", as_of="2026-07-11", nav=500_000)

    class _LiveProvider:
        def load(self):
            return live

    graph = _bare_graph("tw", provider=_LiveProvider())
    snapshot = graph._load_portfolio_snapshot("2026-07-12")
    assert snapshot is live
    assert snapshot.nav == 500_000
