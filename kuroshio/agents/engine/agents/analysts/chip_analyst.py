from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from kuroshio.agents.engine.agents.utils.agent_utils import (
    build_instrument_context,
    get_language_instruction,
)
from kuroshio.agents.engine.agents.utils.chip_data_tools import (
    get_futures_candidates,
    get_institutional_flow,
    get_margin_flow,
)
from kuroshio.agents.engine.agents.utils.i18n import lang_directive


def create_chip_analyst(llm):
    """Create a TW-only chip/institutional-flow analyst node."""

    def chip_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(
            state["company_of_interest"], state.get("asset_type", "stock")
        )
        tools = [get_institutional_flow, get_margin_flow, get_futures_candidates]

        system_message = (
            "You are a Taiwan market chip analyst. Focus on institutional buy/sell "
            "pressure, margin financing/short-sale balance, securities-lending risk, "
            "and whether TAIFEX single-stock futures are available for the same "
            "underlying. Explicitly state whether chip momentum is high, neutral, "
            "or weak, and whether stock futures should be considered for capital "
            "efficiency. "
            "Use the available tools before writing your report. Append a compact "
            "Markdown table with signal, evidence, and implication."
            + get_language_instruction()
            + lang_directive()
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant collaborating with other assistants. "
                    "Use the provided tools to progress toward the analysis. "
                    "You have access to the following tools: {tool_names}.\n"
                    "{system_message}\nFor your reference, the current date is "
                    "{current_date}. {instrument_context}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )
        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)

        result = (prompt | llm.bind_tools(tools)).invoke(state["messages"])
        report = result.content if len(result.tool_calls) == 0 else ""
        return {"messages": [result], "chip_report": report}

    return chip_analyst_node

