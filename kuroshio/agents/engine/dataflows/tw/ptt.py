"""PTT Stock board (`Stock`) search fetcher for Taiwan ticker sentiment.

PTT (批踢踢) is Taiwan's dominant BBS/forum; the Stock board is the primary
retail-trader venue — the rough TW equivalent of r/wallstreetbets for
Reddit/StockTwits in the US-ticker sentiment analyst. No API exists; this
scrapes the public search page and article pages with stdlib only
(urllib + re/html, no requests/bs4), same convention as ``reddit.py`` and
``stocktwits.py`` in this package.

Search is by bare stock code (PTT titles almost always include it, e.g.
``[標的] 3481 群創``) and, if a Chinese name is supplied, additionally by
name — the two result sets are merged and deduped by article URL, since
name-only posts (no code in the title) exist too.

Failure semantics mirror ``reddit.py`` exactly: a fetch failure returns
``None`` internally (never ``[]``, which means "genuinely no results"), and
that distinction surfaces to the caller as separate markers so a network
blip is never misread as "no one is discussing this ticker" — a case that
matters more for PTT than Reddit, since PTT silence on a heavily-owned TW
stock is itself a stronger (and easily misread) signal.
"""

from __future__ import annotations

import html
import http.client
import logging
import re
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

_BASE = "https://www.ptt.cc"
_SEARCH_URL = _BASE + "/bbs/Stock/search?{qs}"
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
_COOKIE = "over18=1"

# How many of the merged (newest-first) results get a full article-page
# fetch for body text + comment push/boo tally. Keeps total requests per
# call small (<=2 searches + 5 article fetches) — PTT rate-limits
# aggressively-polled clients.
_DETAIL_FETCH_COUNT = 5

_ENTRY_SPLIT = '<div class="r-ent">'
_HREF_RE = re.compile(r'<a href="([^"]+)">(.*?)</a>', re.DOTALL)
_NREC_RE = re.compile(r'<div class="nrec">(?:<span[^>]*>([^<]*)</span>)?')
_DATE_RE = re.compile(r'<div class="date">\s*([^<]*)</div>')
_DATE_PARSE_RE = re.compile(r"(\d+)/(\d+)")
_METALINE_RE = re.compile(r'<div class="article-metaline[^"]*">.*?</div>', re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_PUSH_TAG_RE = re.compile(r'push-tag">(推|噓|→)')


def _bare_code(ticker: str) -> str:
    """"3481.TW" / "6488.TWO" -> "3481" / "6488"."""
    upper = ticker.strip().upper()
    for suffix in (".TW", ".TWO"):
        if upper.endswith(suffix):
            return upper[: -len(suffix)]
    return upper


def _get(url: str, timeout: float) -> str | None:
    req = Request(url, headers={"User-Agent": _UA, "Cookie": _COOKIE})
    try:
        with urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except (OSError, http.client.HTTPException) as exc:
        # OSError covers URLError/TimeoutError/connection resets; HTTPException
        # covers chunked-transfer errors (IncompleteRead/BadStatusLine).
        logger.warning("PTT fetch failed for %s: %s", url, exc)
        return None


def _search(query: str, limit: int, timeout: float) -> list[dict] | None:
    """Search the Stock board. ``None`` = fetch failed, ``[]`` = no results.

    Search-result rows are newest-first, so the first ``limit`` rows parsed
    are already the newest ``limit`` results.
    """
    url = _SEARCH_URL.format(qs=urlencode({"q": query}))
    body = _get(url, timeout)
    if body is None:
        return None

    posts = []
    for chunk in body.split(_ENTRY_SPLIT)[1:]:
        href_match = _HREF_RE.search(chunk)
        if not href_match:
            continue  # deleted article: title is placeholder text, no <a>
        url_path, title_html = href_match.groups()
        title = html.unescape(_TAG_RE.sub("", title_html)).strip()
        nrec_match = _NREC_RE.search(chunk)
        # nrec is a raw push-count badge: a number, "爆" (>=100 net push),
        # or "X1".."X9"/"XX" (net-negative / heavily booed). Displayed as-is.
        nrec = (nrec_match.group(1) or "").strip() if nrec_match else ""
        date_match = _DATE_RE.search(chunk)
        date = date_match.group(1).strip() if date_match else "?"
        posts.append({
            "title": title,
            "url": url_path if url_path.startswith("http") else _BASE + url_path,
            "nrec": nrec,
            "date": date,
        })
        if len(posts) >= limit:
            break
    return posts


def _date_sort_key(post: dict) -> tuple[int, int]:
    # ponytail: month/day only, no year (PTT search doesn't show one), so a
    # merge that crosses a year boundary sorts wrong; PTT already serves
    # each individual query newest-first, so this only affects the
    # code+name merge ordering, not per-query correctness. Fix if this
    # dataflow is ever run across Dec/Jan.
    m = _DATE_PARSE_RE.match(post["date"])
    return (int(m.group(1)), int(m.group(2))) if m else (-1, -1)


def _extract_body(article_html: str) -> str:
    tag_start = article_html.find('<div id="main-content"')
    if tag_start == -1:
        return ""
    tag_end = article_html.find(">", tag_start)
    if tag_end == -1:
        return ""
    content = article_html[tag_end + 1:]
    cut = content.find("發信站")
    if cut != -1:
        content = content[:cut]
    content = _METALINE_RE.sub("", content)  # author/board/title/time header
    text = html.unescape(_TAG_RE.sub(" ", content))
    text = " ".join(text.split())
    return text[:280] + "…" if len(text) > 280 else text


def _fetch_article(url: str, timeout: float) -> tuple[int, int, int, str] | None:
    """Returns (push_count, boo_count, arrow_count, body_excerpt), or None on failure."""
    body = _get(url, timeout)
    if body is None:
        return None
    tags = _PUSH_TAG_RE.findall(body)
    push = tags.count("推")
    boo = tags.count("噓")
    arrow = tags.count("→")
    return push, boo, arrow, _extract_body(body)


def fetch_ptt_stock_posts(
    ticker: str,
    stock_name: str | None = None,
    limit: int = 8,
    timeout: float = 10.0,
    inter_request_delay: float = 1.0,
) -> str:
    """Fetch recent PTT Stock-board posts mentioning ``ticker`` and return
    them as a formatted plaintext block ready for prompt injection.

    Searches by bare code, and additionally by ``stock_name`` if given
    (merged, deduped by article URL). The top ``_DETAIL_FETCH_COUNT``
    results (newest first) get a full article-page fetch for a body excerpt
    and a 推/噓/→ comment tally; the rest are listed title-only with PTT's
    own search-page push badge. Never raises.
    """
    code = _bare_code(ticker)
    queries = [code]
    if stock_name and stock_name.strip():
        queries.append(stock_name.strip())

    query_desc = " / ".join(queries)
    results = []
    failed = 0
    first_request = True
    for q in queries:
        if not first_request:
            time.sleep(inter_request_delay)
        first_request = False
        posts = _search(q, limit, timeout)
        results.append((q, posts))
        if posts is None:
            failed += 1

    if failed == len(queries):
        return (
            "<PTT DATA UNAVAILABLE — Stock board search failed/blocked this run for"
            f" \"{query_desc}\". This is a data-pipeline failure: do NOT interpret it"
            " as low retail interest or 'PTT silence'. Base the sentiment read on the"
            " other sources.>"
        )

    notes = [
        f"<FETCH FAILED for PTT search \"{q}\" — treat as MISSING DATA, not as"
        " absence of discussion>"
        for q, posts in results
        if posts is None
    ]

    merged = []
    seen_urls = set()
    for _, posts in results:
        for p in posts or []:
            if p["url"] in seen_urls:
                continue
            seen_urls.add(p["url"])
            merged.append(p)
    merged.sort(key=_date_sort_key, reverse=True)
    merged = merged[:limit]

    if not merged:
        block = f"<no PTT Stock posts found for {query_desc}>"
        return "\n\n".join(notes + [block]) if notes else block

    detail_count = min(_DETAIL_FETCH_COUNT, len(merged))
    total_push = total_boo = 0
    lines = []
    for i, post in enumerate(merged):
        if i < detail_count:
            time.sleep(inter_request_delay)  # paces every article fetch, incl. the first
            detail = _fetch_article(post["url"], timeout)
        else:
            detail = None

        if detail is not None:
            push, boo, _arrow, excerpt = detail
            total_push += push
            total_boo += boo
            tag = f"推{push}/噓{boo}"
            line = f"  [{post['date']} · {tag}] {post['title']}"
            if excerpt:
                line += f"\n    body excerpt: {excerpt}"
        else:
            # Not among the detail-fetch slice, or that article's fetch
            # failed individually — degrade to a title-only row using PTT's
            # own search-page push badge instead of dropping the post.
            badge = post["nrec"] or "?"
            line = f"  [{post['date']} · nrec:{badge}] {post['title']}"
        lines.append(line)

    header = (
        f"PTT Stock 板 — {len(merged)} posts found for {query_desc}"
        f" (top {detail_count} fetched with comment tallies; aggregate 推{total_push}/噓{total_boo}):"
    )
    block = "\n".join([header] + lines)
    return "\n\n".join(notes + [block]) if notes else block
