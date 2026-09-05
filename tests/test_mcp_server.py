"""No-network tests for kuroshio.mcp_server (TASK-10) — the stdio MCP server that
exposes the engine's dataflows, screen/propose, and record_rating for a Claude
Code session. Requires the optional ``mcp`` extra; skipped otherwise."""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("mcp")

from kuroshio.core import ledger  # noqa: E402
from kuroshio.mcp_server import build_server  # noqa: E402
from tests.test_cli import _SPECS, _tw_panel, _use_stub  # noqa: E402

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"

_EXPECTED_TOOLS = {
    "get_stock_data", "get_indicators", "get_fundamentals", "get_balance_sheet",
    "get_cashflow", "get_income_statement", "get_analyst_estimates",
    "get_insider_transactions", "get_news", "get_global_news", "get_macro_indicators",
    "screen", "propose", "record_rating",
}


def _tool_fn(server, name):
    return server._tool_manager.get_tool(name).fn


# --- build_server: no LLM/graph machinery, ever --------------------------------


def test_build_server_never_imports_llm_clients_or_graph():
    """Process-isolated (sys.modules is shared across the whole pytest run, so any
    other test file that already imported the engine's graph/llm_clients would make
    an in-process check pass or fail for the wrong reason)."""
    script = (
        "import sys\n"
        "from kuroshio.mcp_server import build_server\n"
        "build_server()\n"
        "bad = [m for m in sys.modules if m.startswith('kuroshio.agents.engine.llm_clients') "
        "or m.startswith('kuroshio.agents.engine.graph')]\n"
        "print(','.join(bad))\n"
    )
    repo_root = Path(__file__).resolve().parent.parent
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, cwd=str(repo_root)
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "", f"unexpected modules imported: {result.stdout.strip()}"


# --- tool registration ----------------------------------------------------------


def test_tool_list_contains_every_declared_tool():
    server = build_server()
    tools = asyncio.run(server.list_tools())
    names = {t.name for t in tools}
    assert _EXPECTED_TOOLS <= names


# --- record_rating ---------------------------------------------------------------


def test_record_rating_writes_a_row_with_source_and_model(tmp_path, monkeypatch):
    monkeypatch.setenv("KUROSHIO_LEDGER_DIR", str(tmp_path))
    server = build_server()
    record_rating = _tool_fn(server, "record_rating")

    path = record_rating(
        "AAPL", "2026-09-05", "Buy",
        stop_loss=180.0, price_target=220.0, close=200.0, model="claude-sonnet-4-5",
    )

    rows = ledger.load(Path(path))
    assert len(rows) == 1
    assert rows[0] == {
        "date": "2026-09-05", "market": "us", "ticker": "AAPL", "rating": "Buy",
        "stop_loss": 180.0, "price_target": 220.0, "close": 200.0,
        "source": "claude-session", "model": "claude-sonnet-4-5",
    }


def test_record_rating_rejects_an_unknown_rating_and_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("KUROSHIO_LEDGER_DIR", str(tmp_path))
    server = build_server()
    record_rating = _tool_fn(server, "record_rating")

    out = record_rating("AAPL", "2026-09-05", "strong buy")

    assert out.startswith("error:")
    assert not (tmp_path / ledger.RATINGS).exists()


# --- screen / propose: reuse the engine's own stub-provider path ----------------


def test_screen_returns_json_rows(monkeypatch):
    _use_stub(monkeypatch, _tw_panel())
    server = build_server()
    screen = _tool_fn(server, "screen")

    out = screen("tw", ",".join(_SPECS))
    rows = json.loads(out)

    assert rows
    assert all({"ticker", "rank", "final_score"} <= row.keys() for row in rows)


def test_propose_returns_a_string(tmp_path, monkeypatch):
    _use_stub(monkeypatch, _tw_panel())
    holdings = tmp_path / "holdings.yml"
    holdings.write_text("".join(f'- {{ticker: "{t}", weight: 0.05, score: 0.4}}\n' for t in _SPECS))
    server = build_server()
    propose = _tool_fn(server, "propose")

    out = propose(str(EXAMPLES / "ips-balanced.md"), str(holdings), "tw")

    assert isinstance(out, str)
    assert out
