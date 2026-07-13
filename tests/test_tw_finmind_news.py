"""Self-check for the tinboker-backed TW get_news/get_global_news adapter.

No live network — monkeypatches _wiki_get with canned payloads.
"""

from kuroshio.agents.engine.dataflows.tw import finmind

_CONTEXT_PAYLOAD = {
    "topic": "2330",
    "excerpts": [
        {
            "page_kind": "news_article",
            "source_url": "https://cnyes.com/news/12345",
            "date": "2026-07-12",
            "text": "TSMC HBM breakthrough boosts outlook.",
        }
    ],
}

_NEWS_PAYLOAD = {
    "total": 1,
    "articles": [
        {
            "title": "HBM breakthrough",
            "source": "cnYES",
            "date": "2026-07-12",
            "url": "https://cnyes.com/news/12345",
            "tickers": ["2330", "NVDA"],
        }
    ],
}


def test_get_news_formats_excerpts(monkeypatch):
    monkeypatch.setattr(finmind, "_wiki_get", lambda path, **params: _CONTEXT_PAYLOAD)
    out = finmind.get_news("2330.TW", "2026-07-01", "2026-07-13")
    assert "TSMC HBM breakthrough boosts outlook." in out
    assert "cnyes.com" in out
    assert "https://cnyes.com/news/12345" in out
    assert "2330" in out


def test_get_news_no_coverage(monkeypatch):
    monkeypatch.setattr(finmind, "_wiki_get", lambda path, **params: None)
    out = finmind.get_news("2330.TW", "2026-07-01", "2026-07-13")
    assert "No recent Taiwan news found for 2330" in out


def test_get_global_news_formats_articles(monkeypatch):
    monkeypatch.setattr(finmind, "_wiki_get", lambda path, **params: _NEWS_PAYLOAD)
    out = finmind.get_global_news("2026-07-13")
    assert "HBM breakthrough" in out
    assert "cnYES" in out
    assert "2330, NVDA" in out
    assert "https://cnyes.com/news/12345" in out


if __name__ == "__main__":
    import types

    class _Monkeypatch:
        def setattr(self, obj, name, value):
            setattr(obj, name, value)

    mp = _Monkeypatch()
    test_get_news_formats_excerpts(mp)
    test_get_news_no_coverage(mp)
    test_get_global_news_formats_articles(mp)
    print("OK")
