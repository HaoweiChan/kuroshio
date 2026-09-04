"""Discord webhook notifier — posts ProposalCards as embeds.

Integrations are the edge (see ARCHITECTURE.md design rule 3: core never
imports vendors), so this module imports ``requests`` lazily. Needs the
``finmind`` or ``agents`` extra installed (either pulls in ``requests``),
or ``requests`` on its own.
"""

from __future__ import annotations

import logging

from kuroshio.types import ProposalCard

_COLORS = {
    "SWAP": 0x2ECC71, "TRIM": 0xE67E22, "SCALE": 0xF1C40F, "ALERT": 0xE74C3C, "DECIDE": 0x9B59B6,
}
_MAX_EMBEDS = 10  # Discord webhook API limit per payload


def _embed(card: ProposalCard) -> dict:
    # Reuse to_markdown() rather than re-deriving the headline: line 0 is
    # "### {head}", line 1 is blank, the rest is reason + bullet clauses.
    lines = card.to_markdown().split("\n")
    return {"title": lines[0][4:], "description": "\n".join(lines[2:]), "color": _COLORS[card.action]}


def _payload(cards: list[ProposalCard], title: str) -> list[dict]:
    """Pure payload builder — no network, so it's cheap to unit test."""
    embeds = [_embed(c) for c in cards]
    batches = [embeds[i : i + _MAX_EMBEDS] for i in range(0, len(embeds), _MAX_EMBEDS)]
    return [{"content": title if i == 0 else "", "embeds": batch} for i, batch in enumerate(batches)]


def post_cards(webhook_url: str, cards: list[ProposalCard], title: str = "Kuroshio proposals") -> bool:
    """POST proposal cards to a Discord webhook. Never raises — a notification
    failure must not kill a pipeline run; logs and returns False instead."""
    if not cards:
        return True
    try:
        import requests

        for payload in _payload(cards, title):
            resp = requests.post(webhook_url, json=payload, timeout=15)
            resp.raise_for_status()
        return True
    except Exception as e:
        logging.warning("discord webhook post failed: %s", e)
        return False
