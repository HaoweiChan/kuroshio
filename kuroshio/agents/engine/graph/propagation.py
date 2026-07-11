# TradingAgents/graph/propagation.py

from typing import Any

from kuroshio.agents.engine.agents.utils.agent_states import (
    InvestDebateState,
    RiskDebateState,
)


class Propagator:
    """Handles state initialization and propagation through the graph."""

    def __init__(self, max_recur_limit=100):
        """Initialize with configuration parameters."""
        self.max_recur_limit = max_recur_limit

    def create_initial_state(
        self,
        company_name: str,
        trade_date: str,
        asset_type: str = "stock",
        market_region: str = "us",
        past_context: str = "",
        portfolio_snapshot: dict[str, Any] | None = None,
        instrument_candidates: list[dict[str, Any]] | None = None,
        instrument_context: str = "",
        seed_reports: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Create the initial state for the agent graph.

        ``instrument_context`` is the deterministic ticker-identity string
        resolved once at run start (see
        ``TradingAgentsGraph.resolve_instrument_context``). When empty, agents
        fall back to ticker-only context via
        ``get_instrument_context_from_state``.

        ``seed_reports`` (Kuroshio Phase 1 F1) prefills report fields (keyed
        by state key, e.g. ``"market_report"``) from the facet cache for
        analysts that were skipped this run — the corresponding analyst node
        is simply not in the compiled graph, so its report field would
        otherwise stay empty. ``None``/missing keys default to ``""``,
        identical to the pre-F1 behavior.
        """
        seed_reports = seed_reports or {}
        return {
            "messages": [("human", company_name)],
            "company_of_interest": company_name,
            "asset_type": asset_type,
            "market_region": market_region,
            "instrument_context": instrument_context,
            "trade_date": str(trade_date),
            "past_context": past_context,
            "portfolio_snapshot": portfolio_snapshot or {},
            "instrument_candidates": instrument_candidates or [],
            "analyst_signals": {},
            "investment_debate_state": InvestDebateState(
                {
                    "bull_history": "",
                    "bear_history": "",
                    "history": "",
                    "current_response": "",
                    "judge_decision": "",
                    "count": 0,
                }
            ),
            "risk_debate_state": RiskDebateState(
                {
                    "aggressive_history": "",
                    "conservative_history": "",
                    "neutral_history": "",
                    "history": "",
                    "latest_speaker": "",
                    "current_aggressive_response": "",
                    "current_conservative_response": "",
                    "current_neutral_response": "",
                    "judge_decision": "",
                    "count": 0,
                }
            ),
            "market_report": seed_reports.get("market_report", ""),
            "fundamentals_report": seed_reports.get("fundamentals_report", ""),
            "sentiment_report": seed_reports.get("sentiment_report", ""),
            "news_report": seed_reports.get("news_report", ""),
            "chip_report": seed_reports.get("chip_report", ""),
            "strategy_payload": {},
        }

    def get_graph_args(self, callbacks: list | None = None) -> dict[str, Any]:
        """Get arguments for the graph invocation.

        Args:
            callbacks: Optional list of callback handlers for tool execution tracking.
                       Note: LLM callbacks are handled separately via LLM constructor.
        """
        config = {"recursion_limit": self.max_recur_limit}
        if callbacks:
            config["callbacks"] = callbacks
        return {
            "stream_mode": "values",
            "config": config,
        }
