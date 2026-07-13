# Adding a market

Adding a market to kuroshio is one registry entry plus one screening module.
Walking through what a hypothetical `jp` (Japan) market needs, pointing at the
real `tw` market (FinMind) throughout as the worked example to copy from.

## 1. A data source

Implement `kuroshio.providers.base.MarketDataProvider`:

```python
class MarketDataProvider(ABC):
    name: str
    def fetch_panel(self, tickers: list[str], lookback_days: int, end: str | None = None) -> Panel: ...
    def fetch_fundamentals(self, ticker: str) -> dict | None: ...   # optional
```

`tw` uses `kuroshio/providers/finmind.py` — plain `requests` against the FinMind
REST API for OHLCV plus 三大法人 (institutional net-buy) flows, no SDK, token via
`FINMIND_TOKEN` env. If your market's data is on Yahoo Finance, reuse
`kuroshio/providers/yf.py` instead (see `us`'s registry entry) — no new provider
needed. Register a new provider in `kuroshio/providers/__init__.py`'s `_REGISTRY`
dict; imports there are lazy, so an unused provider's SDK never has to be installed.

## 2. A screening profile module

Add `kuroshio/core/screening/jp.py` with:

```python
def screen(panel: Panel, asof: str | None = None, **options) -> list[Candidate]: ...
def score_names(panel: Panel, tickers: Sequence[str], asof: str | None = None, **options) -> list[Candidate]: ...
```

`score_names` (Fix 2, kuroshio<->hermes glue) is `screen`'s Stage-1 gate bypassed —
same factor weights/pctrank/`weighted_score`, scored for exactly the requested
`tickers` instead of the whole gate-passing universe. Used by the allocator's
"weakest incumbent" ranking, which needs a score for held names even when they
aren't a fresh breakout. The lazy, safe way to add it: factor `screen`'s body into
a shared `_screen_or_score(panel, asof, gate: bool, tickers=None, **options)` and
have both public functions call it (see `tw.py`/`us.py`) — don't fork a second
scoring formula.

Use `tw.py` as the template:

- **Universe filter** (`passes_universe`): a pure ticker-string predicate — TW's is
  "4 digits, not `00`-prefixed (excludes ETFs), no letters (excludes warrants)".
- **Stage-1 gates** (`compute_stage1_metrics`): hard pass/fail filters over a
  chronological window of `dates`/`closes`/`volumes` ending on the target day
  (MA uptrend, breakout-high, volume-surge floor, overheated-return filter). Return
  `None` on any failed gate or insufficient history — dropped tickers never score.
- **Cross-sectional pctrank scoring**: gate-passers are ranked against each other
  with `score.pctrank` per factor, combined via `score.weighted_score(scores, WEIGHTS)`.
- **Graceful degradation** (ARCHITECTURE.md rule 4): if a factor's data is missing
  for some/all tickers (TW's institutional flows), don't fake a value — drop it from
  that candidate's `scores` and let `weighted_score` renormalize; flag
  `flags["degraded"]` so the CLI's notice line fires. See `tw.screen`'s
  `global_degraded`/`ticker_degraded` handling (no feed at all, empty feed, one
  ticker missing from an otherwise-healthy feed).

`screen` must stay pure (no network, no DB), and adding `jp.py` must not change
`tw.screen` / `us.screen`'s signatures or math.

## 3. One `MarketProfile` registry entry

In `kuroshio/core/screening/__init__.py`, add one line to `PROFILES`:

```python
"jp": MarketProfile("jp", jp.screen, jp.score_names, "yfinance", lookback_days, warmup_days, min_history, benchmark),
```

- `name` — registry key; also what `--market` accepts on the CLI.
- `screen` — your module's `screen` function, referenced directly.
- `score_names` — your module's `score_names` function (see §2) — the ungated
  counterpart used for incumbent scoring.
- `default_provider` — `kuroshio.providers` registry name used when `--provider` is omitted.
- `lookback_days` — calendar days a single `screen` fetch needs: your longest MA
  window in trading sessions × ~7/5 (weekends) plus slack (TW's `MA_LONG=60` → `120`;
  US's `MA_LONG=200` → `320`).
- `warmup_days` — same idea, for `backtest`'s indicator warmup before its first
  rebalance, on top of the walk-forward horizon (TW → `200`, US → `420`).
- `min_history` — trading *sessions* before `backtest`'s first rebalance; normally
  your Stage-1 gate's `MIN_SESSIONS`/`MA_LONG`.
- `benchmark` — reference ticker auto-added to fetches, used by `walkforward` for
  excess return; `None` if the market has none (TW).
- `accepts_sector_map` — `True` only if `screen` takes a `sector_map` kwarg
  (US-style sector-rotation factor); default `False`.

`cmd_screen`/`cmd_backtest` in `kuroshio/cli.py` read provider default, lookback,
benchmark, and screen kwargs off the profile — no CLI changes needed.

## 4. Tests

Copy the shape of `tests/test_screening.py`'s `tw` tests: a synthetic `Panel`
builder, an uptrend-passes/downtrend-rejected test, a universe-filter exclusion
test, and — if a factor can go missing — the degraded-data tests (see
`test_tw_screen_degrades_without_institutional` and neighbors). Add a
`get_profile("jp")` check alongside `get_profile("us")`/`get_profile("tw")`:
profile resolves, `screen` is callable, `default_provider` is a known provider name.
