"""US Portfolio Manager wrapper."""

from kuroshio.agents.engine.agents.managers.portfolio_manager import create_portfolio_manager


def create_portfolio_manager_us(llm):
    return create_portfolio_manager(llm)

