"""`kuroshio site` — the four page types, the one stylesheet, and the label table.

Also the fixture hygiene check (TASK-13 AC #4): nothing under tests/fixtures/ may carry a
real NAV, a real broker's symbol list, or an absolute path.
"""

from __future__ import annotations

import json
import re
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
FIXTURE_WORDS = {"NAV", "PM", "EQUITY", "ETF", "R"}


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


def test_gitignore_covers_the_default_output_directories_only_at_the_repo_root():
    """`book/` and `site/` unanchored would also ignore `kuroshio/site/` — the package itself."""
    lines = (ROOT / ".gitignore").read_text().splitlines()
    assert "/book/" in lines and "/site/" in lines
    assert "book/" not in lines and "site/" not in lines
