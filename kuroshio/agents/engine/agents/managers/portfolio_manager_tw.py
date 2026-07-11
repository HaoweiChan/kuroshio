"""Taiwan Portfolio Manager with SSF-aware context."""

from __future__ import annotations

import json

from kuroshio.agents.engine.agents.schemas import PortfolioDecision, render_pm_decision
from kuroshio.agents.engine.agents.utils.agent_utils import (
    build_instrument_context,
    get_language_instruction,
    get_long_only_instruction,
)
from kuroshio.agents.engine.agents.utils.i18n import lang_directive
from kuroshio.agents.engine.agents.utils.structured import (
    bind_structured,
    invoke_structured_or_freetext,
)


def create_portfolio_manager_tw(llm):
    structured_llm = bind_structured(llm, PortfolioDecision, "Taiwan Portfolio Manager")

    def portfolio_manager_node(state) -> dict:
        instrument_context = build_instrument_context(
            state["company_of_interest"], state.get("asset_type", "stock")
        )
        risk_debate_state = state["risk_debate_state"]
        portfolio_snapshot = state.get("portfolio_snapshot", {})
        candidates = state.get("instrument_candidates", [])

        prompt = f"""As the Taiwan Portfolio Manager, synthesize the risk analysts' debate and deliver the final trading decision.

{instrument_context}

You must consider both cash equity (現股) and TAIFEX single-stock futures (股期/SSF) for the same underlying when futures candidates are available. Do not force futures exposure; deterministic portfolio sizing will enforce the final 7.5% NAV initial-margin cap after your recommendation.

**Rating Scale** (use exactly one):
- **Buy**: Strong conviction to enter or add to position
- **Overweight**: Favorable outlook, gradually increase exposure
- **Hold**: Maintain current position, no action needed
- **Underweight**: Reduce exposure, take partial profits
- **Sell**: Exit position or avoid entry

**Context:**
- Research Manager's investment plan: **{state["investment_plan"]}**
- Trader's transaction proposal: **{state["trader_investment_plan"]}**
- Portfolio snapshot: {json.dumps(portfolio_snapshot, ensure_ascii=False)}
- TAIFEX candidates: {json.dumps(candidates, ensure_ascii=False)}

**Risk Analysts Debate History:**
{risk_debate_state["history"]}

Be decisive and ground every conclusion in specific evidence from the analysts. If futures are attractive, mention why; if stock shares are safer, say so plainly.{get_long_only_instruction()}{get_language_instruction()}{lang_directive()}"""

        final_trade_decision = invoke_structured_or_freetext(
            structured_llm,
            llm,
            prompt,
            render_pm_decision,
            "Taiwan Portfolio Manager",
        )

        new_risk_debate_state = {
            "judge_decision": final_trade_decision,
            "history": risk_debate_state["history"],
            "aggressive_history": risk_debate_state["aggressive_history"],
            "conservative_history": risk_debate_state["conservative_history"],
            "neutral_history": risk_debate_state["neutral_history"],
            "latest_speaker": "Judge",
            "current_aggressive_response": risk_debate_state["current_aggressive_response"],
            "current_conservative_response": risk_debate_state["current_conservative_response"],
            "current_neutral_response": risk_debate_state["current_neutral_response"],
            "count": risk_debate_state["count"],
        }

        return {
            "risk_debate_state": new_risk_debate_state,
            "final_trade_decision": final_trade_decision,
        }

    return portfolio_manager_node

