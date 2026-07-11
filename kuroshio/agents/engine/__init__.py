"""Kuroshio agents engine — componentized from TradingAgents (Apache 2.0).

``TradingAgentsGraph`` is exposed lazily (PEP 562 module ``__getattr__``) so
importing ``kuroshio.agents.engine`` doesn't pull in langgraph/langchain
until the engine is actually instantiated.
"""

from typing import Any

__all__ = ["TradingAgentsGraph"]


def __getattr__(name: str) -> Any:
    if name == "TradingAgentsGraph":
        from .graph.trading_graph import TradingAgentsGraph

        return TradingAgentsGraph
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
