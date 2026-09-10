"""`kuroshio book` / `kuroshio site` end to end: files in, files out, no fixed locations."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from kuroshio import cli

ROOT = Path(__file__).parent.parent
FIX = ROOT / "tests" / "fixtures"
IPS = str(ROOT / "examples" / "ips-balanced.md")


@pytest.fixture
def no_network(monkeypatch):
    """propose is the only part of `book` that would fetch prices — stub it, not the network."""
    calls = {}

    def fake(ips_path, holdings_path, market, **kw):
        calls["ips"], calls["holdings"], calls["market"] = ips_path, holdings_path, market
        return [], None

    monkeypatch.setattr(cli, "_run_propose", fake)
    return calls


def _book_argv(out: Path, *extra: str) -> list[str]:
    return [
        "book", "--screen", str(FIX / "screen.json"), "--ratings", str(FIX / "ratings.jsonl"),
        "--ips", IPS, "--out", str(out), *extra,
    ]


def test_book_writes_its_five_files_and_nothing_else(tmp_path, no_network, capsys):
    out = tmp_path / "book"
    assert cli.main(_book_argv(
        out, "--scores", str(FIX / "scores.jsonl"), "--meta", str(FIX / "meta.json"),
        "--nav", "100000", "--positions", str(FIX / "positions.csv"),
        "--pm-size", str(FIX / "pm_size.json"), "--locked", str(FIX / "locked.json"),
    )) == 0
    assert sorted(p.name for p in out.iterdir()) == [
        "alloc.md", "book.json", "book.md", "holdings.yml", "needs_research.json", "propose.out",
    ]
    book = json.loads((out / "book.json").read_text())
    assert [r["ticker"] for r in book["core"]] == ["AAA", "BBB", "DDD", "GGG"]
    assert book["alloc"]["nav"] == 100000.0
    assert no_network["holdings"] == str(out / "holdings.yml")  # propose ran on the book's own file
    assert "core 4 · attack 1" in capsys.readouterr().out

    # AC #1: needs_research.json and alloc.md's unrated block name the same tickers, same order
    needs_research = json.loads((out / "needs_research.json").read_text())
    tickers = [r["ticker"] for r in needs_research["research"]]
    assert tickers == ["EEE", "FFF", "HHH"]
    reasons = {r["ticker"]: r["reason"] for r in needs_research["research"]}
    assert reasons["EEE"] == "not researched"
    assert reasons["FFF"] == "rating void: earnings 2026-01-03 after rating 2026-01-02"
    alloc_lines = (out / "alloc.md").read_text().splitlines()
    heading = next(i for i, line in enumerate(alloc_lines) if line.startswith("### Unrated"))
    assert alloc_lines[heading + 2] == ", ".join(
        f"{r['rank']} {r['ticker']}" for r in needs_research["research"]
    )


def test_book_runs_without_positions_scores_or_a_meta_file(tmp_path, no_network):
    out = tmp_path / "book"
    assert cli.main(_book_argv(out)) == 0
    book = json.loads((out / "book.json").read_text())
    assert book["alloc"] is None
    assert not (out / "alloc.md").exists()
    # no industries -> every name is its own theme, so the per-theme cap cuts nobody
    assert {r["ticker"] for r in book["core"]} == {"AAA", "BBB", "DDD", "FFF", "GGG", "III"}


def test_book_rules_are_cli_options(tmp_path, no_network):
    out = tmp_path / "book"
    assert cli.main(_book_argv(
        out, "--meta", str(FIX / "meta.json"), "--scores", str(FIX / "scores.jsonl"),
        "--core-n", "2", "--core-per-theme", "1", "--attack-n", "1", "--attack-budget-pct", "0",
    )) == 0
    book = json.loads((out / "book.json").read_text())
    assert [r["ticker"] for r in book["core"]] == ["AAA", "GGG"]
    assert [r["ticker"] for r in book["attack"]] == ["BBB"]


def test_book_attack_floor_cli_option_skips_below_floor_overflow(tmp_path, no_network):
    """AC #1/#2: `--attack-floor buy` bumps BBB (Overweight) out of the attack sleeve;
    DDD (Buy), the next Widgets overflow by rank, takes the one slot instead."""
    out = tmp_path / "book"
    assert cli.main(_book_argv(
        out, "--meta", str(FIX / "meta.json"), "--scores", str(FIX / "scores.jsonl"),
        "--core-per-theme", "1", "--attack-n", "1", "--attack-budget-pct", "0",
        "--attack-floor", "buy",
    )) == 0
    book = json.loads((out / "book.json").read_text())
    assert [r["ticker"] for r in book["core"]] == ["AAA", "GGG"]
    assert [r["ticker"] for r in book["attack"]] == ["DDD"]
    reason = {r[1]: r[3] for r in book["skipped"]}
    assert reason["BBB"] == "below the attack floor (Overweight)"


def test_book_attack_floor_rejects_an_unknown_value(tmp_path, no_network, capsys):
    out = tmp_path / "book"
    with pytest.raises(SystemExit):
        cli.main(_book_argv(out, "--attack-floor", "strong-buy"))
    assert "invalid choice" in capsys.readouterr().err


def test_book_survives_a_propose_that_cannot_run(tmp_path, monkeypatch):
    def boom(*a, **kw):
        raise RuntimeError("no network here")

    monkeypatch.setattr(cli, "_run_propose", boom)
    out = tmp_path / "book"
    assert cli.main(_book_argv(out)) == 0
    assert "no network here" in (out / "propose.out").read_text()


def test_site_renders_the_book_directory(tmp_path, no_network):
    book, site = tmp_path / "book", tmp_path / "site"
    assert cli.main(_book_argv(
        book, "--meta", str(FIX / "meta.json"), "--nav", "100000",
        "--positions", str(FIX / "positions.csv"),
    )) == 0
    assert cli.main([
        "site", "--book", str(book), "--reports", str(FIX / "reports"), "--out", str(site),
    ]) == 0
    assert (site / "index.html").exists() and (site / "reports" / "BBB" / "2026-01-02.html").exists()


def test_site_lang_option_overrides_the_ips_language(tmp_path, no_network):
    book, site = tmp_path / "book", tmp_path / "site"
    assert cli.main(_book_argv(book)) == 0
    assert cli.main(["site", "--book", str(book), "--out", str(site), "--lang", "zh"]) == 0
    assert "持倉" in (site / "index.html").read_text()
    assert (site / "reports.html").exists()  # a site with no reports still gets the page


def test_site_unknown_lang_falls_back_to_english_instead_of_exiting(tmp_path, no_network):
    """AC #3: an unrecognized `--lang` renders English, matching `book`'s own fallback —
    it must not be an argparse `choices` list that rejects the language outright."""
    book, site = tmp_path / "book", tmp_path / "site"
    assert cli.main(_book_argv(book)) == 0
    assert cli.main(["site", "--book", str(book), "--out", str(site), "--lang", "ja"]) == 0
    index = (site / "index.html").read_text()
    assert "Holdings" in index and "持倉" not in index
