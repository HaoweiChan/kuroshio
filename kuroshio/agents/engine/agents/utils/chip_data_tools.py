from typing import Annotated

from langchain_core.tools import tool

from kuroshio.agents.engine.dataflows.tw import interface as tw_interface


@tool
def get_institutional_flow(
    symbol: Annotated[str, "Taiwan ticker symbol, e.g. 2330.TW or 2330"],
    curr_date: Annotated[str, "Current trading date in yyyy-mm-dd format"],
    look_back_days: Annotated[int, "How many trading days to inspect"] = 20,
) -> str:
    """Retrieve institutional buy/sell flow for a Taiwan ticker."""
    return tw_interface.get_institutional_flow(symbol, curr_date, look_back_days)


@tool
def get_margin_flow(
    symbol: Annotated[str, "Taiwan ticker symbol, e.g. 2330.TW or 2330"],
    curr_date: Annotated[str, "Current trading date in yyyy-mm-dd format"],
    look_back_days: Annotated[int, "How many trading days to inspect"] = 20,
) -> str:
    """Retrieve margin purchase and short-sale flow for a Taiwan ticker."""
    return tw_interface.get_margin_flow(symbol, curr_date, look_back_days)


@tool
def get_futures_candidates(
    symbol: Annotated[str, "Taiwan ticker symbol, e.g. 2330.TW or 2330"],
) -> str:
    """Retrieve TAIFEX single-stock futures candidates for a Taiwan ticker."""
    return tw_interface.get_futures_candidates(symbol)

