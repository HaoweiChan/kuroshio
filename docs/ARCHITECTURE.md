# Kuroshio Architecture

> **Pitch**: TradingAgents for your whole portfolio — run it on your holdings daily, not one ticker once.
> Open-source quantamental engine: quantitative screening funnel + LLM qualitative research
> (facet-cached so daily runs are affordable) + IPS-driven rebalancing **proposals** (never execution).

## Design rules

1. **The engine never executes trades.** Output is always a proposal card. This is both the
   product position and the regulatory safety line.
2. **User IPS content is user data.** The IPS *schema* and presets live here; nobody's actual
   IPS ever enters this repo.
3. **Providers are plugins.** Core logic never imports a data vendor. Everything flows through
   `kuroshio.providers.base`. Default path (`yfinance`) must work with zero API keys.
4. **Graceful degradation.** A market without a data source for some factor (e.g. no
   institutional flows outside TW) renormalizes weights over the available factors and says so
   in the output — it never fakes a value.
5. **Pure compute, thin IO.** Screening/scoring/allocation are pure functions over plain data —
   unit-testable without network or DB. IO lives in providers and the CLI.

## Package layout

```
kuroshio/
├── types.py              # shared dataclasses: Panel, Candidate, Holding, ProposalCard
├── core/
│   ├── screening/        # Stage-1 gates + cross-sectional pctrank scoring, per-market profiles
│   ├── ips/              # IPS schema, parser, presets
│   ├── allocator/        # challenger-vs-incumbent swap proposals
│   └── backtest.py       # walk-forward harness (top-k fwd, rank-IC, quintiles)
├── agents/
│   └── engine/           # LLM research pipeline (TradingAgents-derived) + facet TTL cache
├── providers/            # data-source plugins: base ABC, yfinance (default), finmind (TW)
├── integrations/         # edge adapters: discord webhook notifier
└── cli.py                # `kuroshio screen|backtest|propose|ips-validate|research`
```

## Shared types (`kuroshio/types.py`)

```python
@dataclass
class Panel:
    """Wide OHLCV panel: index = ISO date str (ascending), columns = ticker."""
    close: pd.DataFrame
    volume: pd.DataFrame
    # institutional net-buy shares per (date, ticker); None when the market has no such feed
    institutional: pd.DataFrame | None = None

@dataclass
class Candidate:
    ticker: str
    date: str                    # as-of date, ISO
    rank: int                    # 1 = best
    final_score: float           # [0, 1] weighted pctrank composite
    scores: dict[str, float]     # factor name -> [0,1] pctrank score
    factors: dict[str, float]    # raw sub-metrics (audit trail)
    flags: dict[str, bool]       # e.g. is_60d_high, crowded

@dataclass
class Holding:
    ticker: str
    weight: float                # fraction of NAV, e.g. 0.12
    theme: str | None = None     # sub-theme label, IPS theme-budget key
    leverage: float = 1.0        # >1 for leveraged ETFs: effective exposure = weight × leverage
    score: float | None = None   # latest screener final_score, if screened
    verdict: str | None = None   # latest TA verdict, if researched
    # entry state — why we own this; all optional, absent in pre-T3 holdings files
    entry_price: float | None = None
    entry_date: str | None = None        # ISO date
    setup_type: str | None = None        # value_dip | pullback_add | trend_add | other
    thesis: str | None = None            # free text
    invalidation_price: float | None = None

@dataclass
class ProposalCard:
    action: str                  # "SWAP" | "TRIM" | "ALERT"
    sell: str | None
    buy: str | None
    reason: str                  # one paragraph, human-readable
    ips_clauses: list[str]       # IPS fields that triggered/permitted this, e.g. "caps.theme_pct"
    score_gap: float | None
    friction_pct: float | None   # estimated round-trip cost
    details: dict                # everything else (numbers cited in reason)
```

## `core/screening`

Two market profiles ported from production code, sharing scoring utilities:

- `score.py` — `pctrank(values) -> list[float]` (average-rank ties, n<=1 → 0.0),
  `weighted_score(scores, weights)` which **renormalizes weights over present factors**.
- `tw.py` — TW momentum-breakout profile: Stage-1 gates (close > MA20 & MA60, 20d closing
  high, volume > 1.5× 20d baseline-before-today, 5d return < +20% overheat filter), factors:
  momentum (close/ma20, close/ma60, vol_mult pctranks averaged) 50% + institutional
  concentration (5d 三大法人 net / 20d avg volume) 50%. Universe: 4-digit tickers, no `00`
  prefix (ETFs), no letters (warrants). Flags: is_60d_high, crowded (price_pos_60d > 70).
- `us.py` — US leadership profile: Stage-1 gates (stacked MAs close > MA20 > MA50 > MA200,
  close ≥ 90% of 60d high, 5d return < +25%, price ≥ $5, dollar-volume ≥ $25M), factors:
  momentum .333 / relative-strength-vs-benchmark .267 / volume .20 / sector-rotation .20.

Entry point per profile: `screen(panel: Panel, asof: str | None = None, **profile_kwargs) -> list[Candidate]`.
Pure — no network, no DB. The US sector map is passed in as `sector_map: dict[str, str] | None`
(ticker → sector ETF); sector factor drops out (renormalize) when absent.

Markets are registered, not hardcoded: `MarketProfile` (a frozen dataclass — screen fn,
default provider, lookback/warmup windows, benchmark, whether the profile accepts a sector
map) and the `PROFILES = {"us": ..., "tw": ...}` dict live in `core/screening/__init__.py`;
`get_profile(name)` resolves one or raises `ValueError` listing the known markets. The CLI
reads everything (provider default, fetch lookback, backtest warmup/min-history, benchmark,
screen kwargs) off the profile instead of branching on `market == "us"`. Adding a market is
one registry entry — see `docs/adding-a-market.md`.

## `core/ips`

IPS = one markdown file: YAML frontmatter (machine-readable schema) + free-text philosophy body.

Schema v1 (all optional except `version`; dataclass `IPS` with these fields):

```yaml
version: 1
risk_profile: conservative | balanced | aggressive
style: ""                      # free text, e.g. "momentum breakout, cyclical-aware"
lang: en                       # output language for cards/reports
universe:
  markets: [US, TW]
  exclude: []                  # tickers/patterns never to propose
caps:
  position_pct: 10             # standard max position, % of NAV
  position_hard_pct: 25        # absolute per-name ceiling
  theme_pct: 20                # per-theme effective-exposure budget
  exemptions: []               # [{ticker: "1234", cap: "position_hard_pct", reason: "..."}]
turnover:
  hurdle: 0.15                 # challenger final_score must exceed incumbent by this
  verdict_floor: neutral       # min TA verdict for a challenger (buy>overweight>neutral>underweight>sell ordering)
  max_swaps_per_week: 2
friction:
  tw_roundtrip_pct: 0.585      # default TW tax+fees round trip
  us_roundtrip_pct: 0.02
notify:
  channels: []                 # e.g. [discord, email] — consumed by integrations, not core
```

`parse_ips(path | str) -> IPS` (frontmatter → dataclass, body → `ips.philosophy`),
`validate(ips) -> list[str]` (human-readable problems, empty = valid).
Three presets in `examples/`: ips-conservative.md, ips-balanced.md, ips-aggressive.md.
Unknown keys: preserved in `ips.extra`, never an error (forward compatibility).

## `core/allocator`

`propose(holdings: list[Holding], challengers: list[Candidate], ips: IPS, market: str, verdicts: dict[str, str] | None = None) -> list[ProposalCard]`

Pure function. v1 logic:

1. **Theme budgets**: effective exposure per theme = Σ weight × leverage. Theme over
   `ips.caps.theme_pct` → challengers in that theme may only swap against same-theme
   incumbents; also emit an ALERT card for the breach.
2. **Cap breaches**: holding over `position_hard_pct` (minus exemptions) → TRIM card.
3. **Challenger vs incumbent**: for each challenger not already held and passing
   `verdict_floor`: weakest incumbent (lowest score; unscored incumbents are never
   auto-targeted — emit ALERT suggesting research instead). Propose SWAP when
   `challenger.final_score - incumbent.score ≥ ips.turnover.hurdle` **and** expected edge
   clears friction (`score_gap` must also exceed friction expressed as a score-equivalent —
   gap ≥ hurdle + `friction.{tw,us}_roundtrip_pct` / 100, picked per market, and the card
   cites the friction it cleared).
4. **Never executes.** Cards cite the IPS clause that authorized them ("your IPS §turnover.hurdle = 0.15").
5. Respect `max_swaps_per_week` (caller passes how many were already made via kwarg
   `swaps_this_week: int = 0`).

## `agents/engine` — facet cache

Facet TTL cache — the cost-engineering core. LLM analyst reports are cached per
(ticker, facet) so a daily portfolio run regenerates only stale facets: market/chip/
sentiment/news refresh daily, fundamentals on a TTL (default 7 days). Lives in
`agents/engine/graph/facet_cache.py` (`plan_facets` → stale analyst list + seed
reports; `write_back` persists regenerated ones), production-validated, and wired
into `TradingAgentsGraph.propagate(seed_reports=...)` →
`create_initial_state`. One cache implementation, deliberately — an earlier
standalone `FacetStore` was deleted rather than kept as a second store.

## `providers`

```python
class MarketDataProvider(ABC):
    name: str
    def fetch_panel(self, tickers: list[str], lookback_days: int, end: str | None = None) -> Panel: ...
    def fetch_fundamentals(self, ticker: str) -> dict | None: ...   # optional; default None
```

- `yfinance/` — default, zero keys. Batch download, drop unresolved (all-NaN) columns, drop
  rows where the first ticker's close is NaN (still-forming partial bar). `institutional=None`.
- `finmind/` — TW: OHLCV + 三大法人 (institutional) via FinMind REST (plain `requests`,
  no SDK). Token via `FINMIND_TOKEN` env. Free tier 600 req/hr — batch politely.

Registry: `get_provider(name) -> MarketDataProvider` with lazy imports so optional deps
stay optional.

## CLI (`kuroshio/cli.py`)

argparse, three subcommands (v1):
- `kuroshio screen --market <market> [--provider ...] [--top 20]` — regime-free candidate table.
  `--market` choices and defaults (provider, lookback, benchmark) come from `core.screening.PROFILES`.
- `kuroshio propose --ips path.md --holdings holdings.yml [--market us] [--provider ...]` — proposal
  cards to stdout. A `score:` / `final_score:` missing from the input files is filled from one
  ungated `score_names` cross-section over *the tickers in those files* (one fetch through the
  market's provider); the gated `screen` decides challenger eligibility only, and names it drops
  are reported on stderr. Incumbent and challenger scores therefore come from the same pool —
  the scale-compatibility contract the swap gate needs. That pool is not a universe, so an
  auto-filled score is a percentile among your own names, not a `kuroshio screen` number (no
  `--sector-map`/`--asof` either — see tasks/TODO.md T25/T30); below a pool size of
  `floor(1/turnover.hurdle) + 2` — where pctrank's 1/(n-1) step alone would clear the hurdle —
  nothing is filled and the allocator's ALERT stands. Hand-written values always win, per name.
  Every score hand-typed = no fetch.
- `kuroshio ips-validate path.md`

`holdings.yml`: list of {ticker, weight, theme?, leverage?, score?, verdict?, entry_price?, entry_date?, setup_type?, thesis?, invalidation_price?} — an unknown key is an error naming the key, not a silent drop.
`candidates.yml`: list of {ticker, final_score?, verdict?, theme?} — same rule (`final_scores:` is a typo, not a request to fetch one).

## What deliberately does not exist yet (YAGNI)

- server/, client/, docker-compose — land with the hosted phase.
- Backtest framework — Phase 2 tail.
- Intraday anything; auto-execution (never); multi-tenant glue (never in OSS repo).
