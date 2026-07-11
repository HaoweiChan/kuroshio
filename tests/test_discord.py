"""No-network tests for kuroshio.integrations.discord and its CLI wiring.

_payload is pure (no requests import), so it's tested directly. post_cards'
network path is exercised only for the failure branch, via monkeypatching
requests.post to raise — a real POST never happens in this suite.
"""

from __future__ import annotations

from pathlib import Path

from kuroshio.cli import main
from kuroshio.integrations.discord import _payload, post_cards
from kuroshio.types import ProposalCard

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


# --- _payload ------------------------------------------------------------


def test_payload_single_card():
    cards = [ProposalCard(action="SWAP", reason="better momentum", sell="A", buy="B", score_gap=0.05)]
    payloads = _payload(cards, "Kuroshio proposals")

    assert len(payloads) == 1
    assert payloads[0]["content"] == "Kuroshio proposals"
    embeds = payloads[0]["embeds"]
    assert len(embeds) == 1
    assert embeds[0]["title"] == "SWAP A → B"
    assert "better momentum" in embeds[0]["description"]
    assert "score gap: +0.050" in embeds[0]["description"]
    assert embeds[0]["color"] == 0x2ECC71


def test_payload_colors_by_action():
    cards = [
        ProposalCard(action="SWAP", reason="r", sell="A", buy="B"),
        ProposalCard(action="TRIM", reason="r", sell="A"),
        ProposalCard(action="ALERT", reason="r"),
    ]
    payloads = _payload(cards, "T")
    colors = [e["color"] for e in payloads[0]["embeds"]]
    assert colors == [0x2ECC71, 0xE67E22, 0xE74C3C]


def test_payload_batches_at_eleven_cards():
    cards = [ProposalCard(action="ALERT", reason=f"r{i}") for i in range(11)]
    payloads = _payload(cards, "T")

    assert len(payloads) == 2
    assert len(payloads[0]["embeds"]) == 10
    assert len(payloads[1]["embeds"]) == 1
    assert payloads[0]["content"] == "T"
    assert payloads[1]["content"] == ""  # title only announced once


def test_payload_empty_cards_returns_no_payloads():
    assert _payload([], "T") == []


# --- post_cards ------------------------------------------------------------


def test_post_cards_empty_list_is_noop_and_true(monkeypatch):
    def _boom(*a, **kw):
        raise AssertionError("must not touch network for an empty card list")

    monkeypatch.setattr("requests.post", _boom)
    assert post_cards("https://discord.example/hook", []) is True


def test_post_cards_network_failure_returns_false_without_raising(monkeypatch):
    import requests

    def _raise(*a, **kw):
        raise requests.exceptions.ConnectionError("boom")

    monkeypatch.setattr(requests, "post", _raise)

    cards = [ProposalCard(action="ALERT", reason="r")]
    assert post_cards("https://discord.example/hook", cards) is False


# --- CLI wiring ------------------------------------------------------------


def test_propose_with_discord_webhook_calls_post_cards(tmp_path, capsys, monkeypatch):
    import kuroshio.integrations.discord as discord_mod

    calls = []

    def _fake_post_cards(webhook_url, cards, title="Kuroshio proposals"):
        calls.append((webhook_url, cards))
        return True

    monkeypatch.setattr(discord_mod, "post_cards", _fake_post_cards)

    holdings = tmp_path / "holdings.yml"
    holdings.write_text("- {ticker: OVER, weight: 0.30, score: 0.5}\n")

    code = main(
        [
            "propose",
            "--ips", str(EXAMPLES / "ips-balanced.md"),
            "--holdings", str(holdings),
            "--market", "us",
            "--discord-webhook", "https://discord.example/hook",
        ]
    )
    err = capsys.readouterr().err

    assert code == 0
    assert len(calls) == 1
    assert calls[0][0] == "https://discord.example/hook"
    assert calls[0][1][0].action == "TRIM"
    assert "Discord" in err


def test_propose_no_webhook_flag_leaves_behavior_unchanged(tmp_path, capsys, monkeypatch):
    import kuroshio.integrations.discord as discord_mod

    def _boom(*a, **kw):
        raise AssertionError("post_cards must not be called without --discord-webhook")

    monkeypatch.setattr(discord_mod, "post_cards", _boom)
    monkeypatch.delenv("KUROSHIO_DISCORD_WEBHOOK", raising=False)

    holdings = tmp_path / "holdings.yml"
    holdings.write_text("- {ticker: OVER, weight: 0.30, score: 0.5}\n")

    code = main(
        [
            "propose",
            "--ips", str(EXAMPLES / "ips-balanced.md"),
            "--holdings", str(holdings),
            "--market", "us",
        ]
    )
    err = capsys.readouterr().err

    assert code == 0
    assert err == ""
