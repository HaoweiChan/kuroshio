"""TinBoker podcast-mention dataflow: formatting, track record, failure markers."""

import kuroshio.agents.engine.agents.analysts.sentiment_analyst as sentiment
from kuroshio.agents.engine.dataflows.tw import tinboker

INSIGHTS = [
    {
        "podcaster": "Gooaye 股癌", "podcast_launch_time": "2026-09-05T07:30:33Z",
        "sentiment_label": "BULLISH", "time_horizon": "長期", "bluf_thesis": "AI 核心基石",
        "reasons": [{"title": "大客戶持續下單"}, {"title": "EPS 趨勢向上"}],
        "risks": [{"title": "短期股價停滯", "severity": "LOW"}],
    },
]
MENTIONS = [
    {"podcaster": "Gooaye 股癌", "sentiment_label": "BULLISH", "performance": {"r20d": 5.0}},
    {"podcaster": "Gooaye 股癌", "sentiment_label": "BULLISH", "performance": {"r20d": -2.0}},
    {"podcaster": "Gooaye 股癌", "sentiment_label": "NEUTRAL", "performance": {"r20d": 3.0}},
    {"podcaster": "Gooaye 股癌", "sentiment_label": "BULLISH", "performance": {"r20d": None}},
    {"podcaster": "財經一路發", "sentiment_label": "BEARISH", "performance": None},
]


def _stub(monkeypatch, insights, mentions):
    monkeypatch.setattr(tinboker, "_fetch_insights", lambda *a: insights)
    monkeypatch.setattr(tinboker, "_fetch_mentions", lambda *a: mentions)


def test_block_lists_theses_and_per_show_track_record(monkeypatch):
    _stub(monkeypatch, INSIGHTS, MENTIONS)
    block = tinboker.fetch_tinboker_mentions("2330.TW", "2026-09-05")
    assert "1 theses on 2330 from 1 shows, 2026-08-06→2026-09-05" in block
    assert "1 bullish / 0 neutral / 0 bearish; newest 1 shown:" in block
    assert "[2026-09-05 · Gooaye 股癌 · BULLISH · 長期] AI 核心基石" in block
    assert "reasons: 大客戶持續下單; EPS 趨勢向上" in block
    assert "risks: 短期股價停滯 (LOW)" in block
    # 4 mentions, 3 resolved, neutral not scored → hit 1/2, mean (5-2+3)/3 = +2.0%
    assert "Gooaye 股癌: 4 mentions, 3 with r20d, directional hit 1/2, mean r20d +2.0%" in block
    assert "財經一路發: 1 mentions, none old enough for a r20d yet" in block


def test_theses_are_capped_but_the_tally_counts_them_all(monkeypatch):
    many = [
        dict(INSIGHTS[0], bluf_thesis=f"t{i}", sentiment_label="BEARISH" if i % 5 == 0 else "BULLISH")
        for i in range(30)
    ]
    _stub(monkeypatch, many, [])
    block = tinboker.fetch_tinboker_mentions("2330.TW", "2026-09-05")
    assert "30 theses on 2330 from 1 shows" in block
    assert "24 bullish / 0 neutral / 6 bearish; newest 12 shown:" in block
    assert block.count("] t") == 12


def test_empty_window_is_reported_as_real_silence(monkeypatch):
    _stub(monkeypatch, [], [])
    block = tinboker.fetch_tinboker_mentions("2330.TW", "2026-09-05")
    assert "real silence, not a fetch failure" in block
    assert "Track record" not in block


def test_both_fetches_failing_is_a_pipeline_marker(monkeypatch):
    _stub(monkeypatch, None, None)
    block = tinboker.fetch_tinboker_mentions("2330.TW", "2026-09-05")
    assert block.startswith("<TINBOKER DATA UNAVAILABLE")


def test_one_fetch_failing_keeps_the_other_and_notes_the_gap(monkeypatch):
    _stub(monkeypatch, None, MENTIONS)
    block = tinboker.fetch_tinboker_mentions("2330.TW", "2026-09-05")
    assert "<FETCH FAILED for TinBoker insights window" in block
    assert "Track record" in block


def test_prompt_includes_section_and_guidance_only_when_given():
    kw = dict(ticker="2330.TW", start_date="2026-08-29", end_date="2026-09-05",
              news_block="n", stocktwits_block="s", reddit_block="r")
    with_block = sentiment._build_system_message(**kw, tinboker_block="BLOCK")
    assert "<start_of_tinboker>\nBLOCK\n<end_of_tinboker>" in with_block
    assert "10. **For TW tickers, the TinBoker block" in with_block
    assert "tinboker" not in sentiment._build_system_message(**kw).lower()
