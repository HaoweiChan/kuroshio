"""Shared graph node helpers for market-specific graph setups."""

from __future__ import annotations

from typing import Any, Callable, Dict

from langchain_core.messages import HumanMessage
from langgraph.prebuilt import ToolNode


def create_isolated_analyst_runner(
    analyst_node: Callable[[Dict[str, Any]], Dict[str, Any]],
    tool_node: ToolNode,
    report_key: str,
    *,
    max_tool_rounds: int = 8,
) -> Callable[[Dict[str, Any]], Dict[str, Any]]:
    """Run an analyst/tool loop without returning branch-local messages.

    This keeps TW fan-out branches from concurrently appending to the shared
    LangGraph ``messages`` reducer. Only the completed report field is merged
    back into the parent graph state.
    """

    def run(state: Dict[str, Any]) -> Dict[str, Any]:
        isolated = dict(state)
        isolated["messages"] = [HumanMessage(content=state["company_of_interest"])]

        for _ in range(max_tool_rounds):
            result = analyst_node(isolated)
            report = result.get(report_key)
            result_messages = result.get("messages", [])
            isolated["messages"] = list(isolated.get("messages", [])) + list(
                result_messages
            )

            if report:
                return {report_key: report}

            last = isolated["messages"][-1] if isolated["messages"] else None
            if last is None or not getattr(last, "tool_calls", None):
                content = getattr(last, "content", "") if last is not None else ""
                return {report_key: content}

            tool_result = tool_node.invoke({"messages": isolated["messages"]})
            isolated["messages"] = isolated["messages"] + list(
                tool_result.get("messages", [])
            )

        return {
            report_key: (
                f"{report_key} did not complete within {max_tool_rounds} tool rounds."
            )
        }

    return run


def fan_in_join(state: Dict[str, Any]) -> Dict[str, Any]:
    """No-op barrier node for analyst fan-in."""
    return {}

