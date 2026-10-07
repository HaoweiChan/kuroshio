"""kuroshio/core/track.py — raw-return record of the saved books, and its site page."""

import json
import re
import shutil

import pandas as pd
import pytest

from kuroshio.core import track
from kuroshio.site import render

DAYS = ["2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07"]
CLOSE = pd.DataFrame(
    {"AAA": [100, 110, 121, 121], "BBB": [50, 50, 40, 44], "SPY": [400, 404, 404, 404]},
    index=pd.to_datetime(DAYS), dtype=float,
)
# day 1 book: AAA core 5%, BBB attack 10%; day 3 book drops BBB
BOOKS = [
    ("2026-01-02", {"AAA": {"weight": 0.05, "sleeve": "core"}, "BBB": {"weight": 0.10, "sleeve": "attack"}}),
    ("2026-01-06", {"AAA": {"weight": 0.05, "sleeve": "core"}}),
]


def test_a_day_is_the_weight_normalised_return_of_that_days_book_not_nav():
    tr = track.track(BOOKS, CLOSE, "SPY")
    by_day = {s["date"]: s for s in tr["series"]}
    # 01-05: AAA +10% at 5, BBB 0% at 10 -> (0.05*0.10)/0.15, cash never dilutes it
    assert by_day["2026-01-05"]["book"] == pytest.approx(0.1 * 0.05 / 0.15, abs=1e-5)
    assert by_day["2026-01-05"]["attack"] == pytest.approx(0.0)
    assert by_day["2026-01-05"]["core"] == pytest.approx(0.10)
    assert by_day["2026-01-05"]["bench"] == pytest.approx(0.01)
    # 01-07: the 01-06 book holds AAA only, flat; BBB's +10% bounce is not counted
    assert by_day["2026-01-07"]["book"] == by_day["2026-01-06"]["book"]


def test_an_episode_exits_at_the_close_of_the_first_book_that_dropped_it():
    eps = {e["ticker"]: e for e in track.track(BOOKS, CLOSE, "SPY")["episodes"]}
    assert eps["BBB"]["exit_date"] == "2026-01-06" and eps["BBB"]["ret"] == pytest.approx(-0.2)
    assert not eps["BBB"]["open"] and eps["BBB"]["sleeves"] == ["attack"]
    assert eps["AAA"]["open"] and eps["AAA"]["ret"] == pytest.approx(0.21) and eps["AAA"]["books"] == 2
    s = track.summary(track.track(BOOKS, CLOSE, "SPY"))
    assert s["n_attack"] == 1 and s["hit_attack"] == 0 and s["hit_core"] == 1


def test_load_books_reads_dated_dirs_only_and_the_current_book_wins(tmp_path):
    def book(asof, t):
        return {"asof": asof, "core": [{"ticker": t, "weight": 0.05}], "attack": []}
    for name, b in (("2026-01-02", book("2026-01-02", "OLD")), ("run-manual", book("2026-01-03", "X"))):
        (tmp_path / name).mkdir()
        (tmp_path / name / "book.json").write_text(json.dumps(b))
    books = track.load_books(tmp_path, current=book("2026-01-02", "NEW"))
    assert books == [("2026-01-02", {"NEW": {"weight": 0.05, "sleeve": "core"}})]


def test_the_site_renders_a_track_page_only_when_track_json_is_there(tmp_path):
    from tests.test_site import FIX, _book_dir

    book_dir = _book_dir(tmp_path)
    out = tmp_path / "site"
    render.render_site(book_dir, FIX / "reports", out)
    assert not (out / "track.html").exists()
    (book_dir / "track.json").write_text(json.dumps(track.track(BOOKS, CLOSE, "SPY")))
    render.render_site(book_dir, FIX / "reports", out, lang="zh")
    page = (out / "track.html").read_text()
    assert "績效" in page and "BBB" in page and "-20.0%" in page and "<polyline" in page
    assert page.count("基準 S&amp;P 500 (SPY)") == 2
    for day in DAYS[1:]:
        assert re.search(r"<text[^>]*>" + day + r"</text>", page)
    english = (out / "en" / "track.html").read_text()
    assert english.count("Benchmark S&amp;P 500 (SPY)") == 2
    # the attack panel states today's rules: risk-scaled top-up and the hysteresis buffer
    assert "自身權重的 2 倍，最多 10%" in page and "最多 2% NAV" in page
    assert "排名在名額數的 2 倍以內" in page and "只要當天排名還把它放在攻擊倉就留著" not in page
    shutil.rmtree(out)


def test_chart_positions_follow_calendar_dates_and_label_the_actual_benchmark():
    series = [dict(date=day, book=0.0, core=0.0, attack=0.0, bench=0.0) for day in DAYS]
    chart = render._track_chart(series, render.labels("en"), "OTHER")
    points = re.search(r"points='([^']+)'", chart).group(1).split()
    xs = [float(point.split(",")[0]) for point in points]
    assert xs[1] - xs[0] == pytest.approx(3 * (xs[2] - xs[1]), abs=0.2)
    assert "Benchmark OTHER" in chart and "SPY" not in chart
    assert chart.count("<text ") == 3
    short = render._track_chart(series[:2], render.labels("en"), "SPY")
    assert short.count("<text ") == 2
    assert render._track_chart([], render.labels("en"), "SPY") == ""
