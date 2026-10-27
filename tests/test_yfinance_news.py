"""get_news_yfinance falls back to yf.Search when Ticker.get_news is empty.

No live network — monkeypatches yfinance with a recorded Search payload.
"""

from datetime import datetime

from kuroshio.agents.engine.dataflows import yfinance_news

_PUB = int(datetime(2026, 10, 26, 12).timestamp())

# Flat Search shape, as Yahoo returned it for "MRNA" on 2026-10-27.
_SEARCH_NEWS = [
    {
        "title": "Moderna Tumbles 7% as Cancer Vaccine Selloff Deepens",
        "publisher": "Benzinga",
        "link": "https://finance.yahoo.com/a/moderna-tumbles.html",
        "providerPublishTime": _PUB,
        "type": "STORY",
        "relatedTickers": ["MRNA", "MRK"],
    },
    {
        "title": "Nasdaq Futures Slip Amid Tech Selloff",
        "publisher": "MT Newswires",
        "link": "https://finance.yahoo.com/a/nasdaq.html",
        "providerPublishTime": _PUB,
        "type": "STORY",
        "relatedTickers": ["^IXIC", "^GSPC"],
    },
]


class _Ticker:
    def __init__(self, symbol):
        pass

    def get_news(self, count=10):
        return []  # what yfinance 1.5.1 returns now that /xhr/ncp 404s


class _Search:
    def __init__(self, query, news_count=8, **kw):
        self.news = _SEARCH_NEWS


def test_get_news_falls_back_to_search(monkeypatch):
    monkeypatch.setattr(yfinance_news.yf, "Ticker", _Ticker)
    monkeypatch.setattr(yfinance_news.yf, "Search", _Search)
    out = yfinance_news.get_news_yfinance("MRNA", "2026-08-28", "2026-10-27")
    assert "Moderna Tumbles 7%" in out
    assert "Nasdaq Futures" not in out  # not tagged MRNA
