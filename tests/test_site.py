"""`kuroshio site` — the four page types, the one stylesheet, and the label table.

Also the fixture hygiene check (TASK-13 AC #4): nothing under tests/fixtures/ may carry a
real NAV, a real broker's symbol list, or an absolute path.
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

import pytest

from kuroshio.core import book as bk
from kuroshio.core.ips import parse_ips
from kuroshio.site import render
from kuroshio.site.labels import LABELS, labels

ROOT = Path(__file__).parent.parent
FIX = ROOT / "tests" / "fixtures"
SYNTHETIC = {"AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG", "HHH", "III", "QQQ", "ZZZ"}
# words that are legitimately upper-case in a fixture and are not ticker symbols
FIXTURE_WORDS = {"NAV", "PM", "EQUITY", "ETF", "R", "US"}


def _book_dir(tmp_path: Path) -> Path:
    book = bk.build_book(
        bk.load_screen(FIX / "screen.json"),
        bk.load_jsonl(FIX / "ratings.jsonl"),
        parse_ips(str(ROOT / "examples" / "ips-balanced.md")),
        meta=json.loads((FIX / "meta.json").read_text()),
        scores_rows=bk.load_jsonl(FIX / "scores.jsonl"),
        positions=bk.load_positions(FIX / "positions.csv"),
        nav=100000.0,
        pm_size=json.loads((FIX / "pm_size.json").read_text()),
        locked=json.loads((FIX / "locked.json").read_text()),
        ips_name="ips-balanced.md",
    )
    out = tmp_path / "book"
    bk.write_book(book, out, propose_text="### SWAP CCC for AAA\n\nsynthetic card\n\n- because tests")
    return out


@pytest.fixture
def site(tmp_path):
    out = tmp_path / "site"
    render.render_site(_book_dir(tmp_path), FIX / "reports", out)
    return out


def test_site_renders_the_four_page_types(site):
    assert (site / "index.html").exists()
    assert (site / "alloc.html").exists()
    assert (site / "reports.html").exists()
    assert (site / "reports" / "AAA" / "2026-01-02.html").exists()

    index = (site / "index.html").read_text()
    assert "AAA" in index and "10.0%" in index and "SWAP CCC for AAA" in index
    assert "reports/AAA/2026-01-02.html" in index  # the book links its report
    alloc = (site / "alloc.html").read_text()
    assert "100,000" in alloc and "QQQ" in alloc
    reports = (site / "reports.html").read_text()
    assert "AAA" in reports and "BBB" in reports
    page = (site / "reports" / "AAA" / "2026-01-02.html").read_text()
    assert "<table>" in page and "synthetic research report" in page


def test_pages_use_relative_links_only(site):
    for page in site.rglob("*.html"):
        for href in re.findall(r"(?:href|src)='([^']+)'", page.read_text()):
            assert not href.startswith("/"), f"{page.name}: absolute link {href}"
            assert "http" not in href or href.startswith("https://github.com/"), href


def test_the_stylesheet_is_one_file_docs_and_the_package_share(site):
    packaged = (Path(render.__file__).parent / "style.css").read_bytes()
    assert packaged == (ROOT / "docs" / "style.css").read_bytes()
    index_html = (ROOT / "docs" / "index.html").read_text()
    assert '<link rel="stylesheet" href="style.css">' in index_html
    assert "<style>" not in index_html  # the design system lives in style.css, nowhere else
    assert ":root {" in (site / "index.html").read_text()  # and the site ships it inline


def test_every_language_defines_every_label_with_the_same_placeholders():
    english = LABELS["en"]
    for lang, table in LABELS.items():
        assert set(table) == set(english), f"{lang}: label keys drifted from en"
        for key, value in table.items():
            assert re.findall(r"\{(\w+)", value) == re.findall(r"\{(\w+)", english[key]), f"{lang}.{key}"


def test_an_unknown_language_falls_back_to_english():
    assert labels("kl") == LABELS["en"]
    assert labels(None) == LABELS["en"]
    assert labels("zh-TW")["holdings_head"] == LABELS["zh"]["holdings_head"]


def test_both_languages_render_every_page(tmp_path):
    for lang in ("en", "zh", "kl"):
        out = tmp_path / f"site-{lang}"
        render.render_site(_book_dir(tmp_path), FIX / "reports", out, lang=lang)
        for page in out.rglob("*.html"):
            text = page.read_text()
            assert "{" not in text.split("<style>")[0]  # no unformatted template outside the CSS
            assert "None" not in re.findall(r">([^<]*)<", text)


def test_a_locked_position_with_no_average_price_renders_na_instead_of_raising(tmp_path):
    """R1: `average_price` is empty for a locked row whenever the broker export carries none
    (a transferred-in position, a DRIP lot, etc) — book.py already carries that through as
    `avg_cost: None`; the site must render the same n/a label book.md/alloc.md already use,
    not TypeError on `None:,.2f`."""
    positions = bk.load_positions(FIX / "positions.csv") + [{
        "symbol": "III", "quantity": 100.0, "market_value": 9000.0,
        "average_price": None, "asset_type": "EQUITY",
    }]
    book = bk.build_book(
        bk.load_screen(FIX / "screen.json"),
        bk.load_jsonl(FIX / "ratings.jsonl"),
        parse_ips(str(ROOT / "examples" / "ips-balanced.md")),
        meta=json.loads((FIX / "meta.json").read_text()),
        scores_rows=bk.load_jsonl(FIX / "scores.jsonl"),
        positions=positions,
        nav=100000.0,
        pm_size=json.loads((FIX / "pm_size.json").read_text()),
        locked={"III": {"theme": "locked-theme", "note": "no cost basis on file"}},
        ips_name="ips-balanced.md",
    )
    out = tmp_path / "book"
    bk.write_book(book, out)
    site = tmp_path / "site"
    render.render_site(out, FIX / "reports", site)  # must not raise TypeError
    index = (site / "index.html").read_text()
    alloc = (site / "alloc.html").read_text()
    assert "III" in index and "n/a" in index
    assert "III" in alloc and "n/a" in alloc


def test_a_failed_build_removes_the_new_directory(tmp_path, monkeypatch):
    """R1: the build happens in `<out>.new` before the atomic swap — a failure partway through
    must not leave that directory on disk."""
    out = tmp_path / "site"

    def boom(*a, **kw):
        raise RuntimeError("boom")

    monkeypatch.setattr(render, "_report_pages", boom)
    with pytest.raises(RuntimeError):
        render.render_site(_book_dir(tmp_path), FIX / "reports", out)
    assert not list(tmp_path.glob("site.*"))
    assert not out.exists()


def test_the_output_directory_is_swapped_not_edited_in_place(tmp_path):
    out = tmp_path / "site"
    out.mkdir()
    (out / "stale.html").write_text("old build")
    render.render_site(_book_dir(tmp_path), FIX / "reports", out)
    assert not (out / "stale.html").exists()
    assert (out / "index.html").exists()
    assert not list(tmp_path.glob("site.*"))  # no half-built or leftover directory


def test_fixtures_carry_no_real_nav_broker_symbols_or_absolute_paths():
    for path in sorted(FIX.rglob("*")):
        if not path.is_file():
            continue
        text = path.read_text()
        where = path.relative_to(ROOT)
        for prefix in ("/Users/", "/home/", "/private/", "/var/folders/", "C:\\"):
            assert prefix not in text, f"{where}: absolute path {prefix}"
        symbols = set(re.findall(r"\b[A-Z]{2,5}\b", text)) - FIXTURE_WORDS
        assert symbols <= SYNTHETIC, f"{where}: non-synthetic symbols {sorted(symbols - SYNTHETIC)}"
    # a real broker export carries cents; the synthetic one is whole round numbers
    for row in bk.load_positions(FIX / "positions.csv"):
        for field in ("quantity", "market_value", "average_price"):
            assert row[field] == int(row[field]), f"positions.csv: {row['symbol']}.{field} looks real"


def test_markdown_is_in_the_dev_extra_so_the_gate_covers_this_renderer():
    """R2: `pytest tests/ -q` runs these markdown-dependent tests, but CI and the documented
    dev install only run `pip install -e ".[agents,yfinance,dev]"` — `markdown` must be listed
    under `dev`, not only under the `site` extra a plain dev install never touches."""
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
    dev_deps = pyproject["project"]["optional-dependencies"]["dev"]
    assert any(dep.split(">=")[0].split("==")[0].strip() == "markdown" for dep in dev_deps), dev_deps


def test_gitignore_covers_the_default_output_directories_only_at_the_repo_root():
    """`book/` and `site/` unanchored would also ignore `kuroshio/site/` — the package itself."""
    lines = (ROOT / ".gitignore").read_text().splitlines()
    assert "/book/" in lines and "/site/" in lines
    assert "book/" not in lines and "site/" not in lines
    # and `reports/` unanchored swallowed tests/fixtures/reports, the site tests' input
    assert "/reports/" in lines and "reports/" not in lines
    assert (FIX / "reports" / "AAA" / "2026-01-02" / "complete_report.md").exists()


# TASK-14: every string the report page adds, in both languages
REPORT_LABELS = (
    "synthesis", "committee_rating", "executive_thesis", "no_summary", "coverage",
    "included", "not_included", "final_posture", "reference_close", "rr_from_close",
    "sizing_dates", "rating_date", "analyst_lenses", "lenses_lede", "lens", "research_desk",
    "bull_vs_bear", "risk_committee", "risk_postures", "decision_trail", "decision_lede",
    "stage", "research_plan", "trader_decision", "final_decision", "tab_overview",
    "tab_research", "tab_debates", "tab_decision", "tab_raw", "empty_head", "empty_lede",
) + tuple(
    f"role_{role}" for role in (
        "market", "sentiment", "news", "fundamentals", "bull", "bear", "manager",
        "trader", "aggressive", "neutral", "conservative", "decision",
    )
)
# a role whose Chinese name is the English one on purpose
SAME_IN_BOTH = {"role_decision"}


def test_every_report_page_label_is_defined_and_translated():
    for key in REPORT_LABELS:
        for lang in ("en", "zh"):
            assert LABELS[lang].get(key), f"{lang}: missing label {key}"
        if key not in SAME_IN_BOTH:
            assert LABELS["zh"][key] != LABELS["en"][key], f"zh.{key} is still the English string"


def _report(site: Path, ticker: str = "AAA", date: str = "2026-01-02") -> str:
    return (site / "reports" / ticker / f"{date}.html").read_text()


def _body(page: str) -> str:
    """The page without the inlined stylesheet — the markup this repo generates."""
    return page.split("</style>", 1)[1]


def test_the_report_page_has_the_hero_five_tabs_and_twelve_coverage_tiles(site):
    """AC #1: the tabbed layout, built from the role files a full report tree carries."""
    body = _body(_report(site))
    assert "report-hero" in body and "hero-verdict" in body
    assert body.count("class='tab-btn") == 5
    assert body.count("class='tab-body") == 5
    assert "thesis-card" in body and "Half a position at the close" in body
    assert body.count("coverage-tile") == 12
    assert body.count("coverage-tile on") == 12  # the fixture carries every role file
    assert body.count("group-heading") == 2  # research desk + risk committee
    assert "verdict-card" in body and "signal-strip" in body and "decision-layout" in body


def test_a_report_with_only_the_complete_report_renders_raw_plus_empty_states(site):
    """AC #1: no role files -> the raw tab still renders, the other three say so."""
    body = _body(_report(site, "BBB", "2026-01-02"))
    assert body.count("class='tab-btn") == 5
    assert "coverage-tile on" not in body
    assert body.count("empty-panel") == 3  # research, debates, decision
    assert "nothing but this file" in body  # complete_report.md still renders


def test_the_report_page_carries_no_hex_colours_outside_the_shared_stylesheet(site):
    """AC #2: every colour is a docs/style.css token."""
    hexes = re.compile(r"#[0-9a-fA-F]{3,6}")
    site_css = (Path(render.__file__).parent / "site.css").read_text()
    assert not hexes.findall(site_css), hexes.findall(site_css)
    for ticker, date in (("AAA", "2026-01-02"), ("BBB", "2026-01-02")):
        found = hexes.findall(_body(_report(site, ticker, date)))
        assert not found, f"{ticker} {date}: {found}"


def test_a_role_file_with_two_sections_becomes_one_content_block_per_section(site):
    """AC #3: PanelizedMarkdown — two or more `## ` sections grid, otherwise one block."""
    body = _body(_report(site))
    assert body.count("report-body-grid") == 8  # 4 analysts + bull/bear/manager (manager twice)
    assert body.count("content-block") == 16
    assert body.count("report-body-single") == 6  # 3 risk views + trader + decision (twice)


def test_the_other_pages_carry_no_report_layout_markup(site):
    """AC #5: index, alloc and reports are task-13's pages — the layout is report-only."""
    for name in ("index.html", "alloc.html", "reports.html"):
        body = _body((site / name).read_text())
        for cls in ("report-hero", "tab-btn", "coverage-tile", "report-card", "verdict-card",
                    "signal-strip", "decision-layout", "empty-panel", "showTab("):
            assert cls not in body, f"{name}: {cls}"
