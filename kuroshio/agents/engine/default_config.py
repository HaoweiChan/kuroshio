import os

_KUROSHIO_HOME = os.path.join(os.path.expanduser("~"), ".kuroshio")

# Single source of truth for env-var → config-key overrides. To expose
# a new config key for environment-based override, add a row here — no
# entry-point script changes required. Coercion is driven by the type
# of the existing default, so users can keep writing plain strings in
# their .env file.
_ENV_OVERRIDES = {
    "KUROSHIO_LLM_PROVIDER":         "llm_provider",
    "KUROSHIO_DEEP_THINK_LLM":       "deep_think_llm",
    "KUROSHIO_QUICK_THINK_LLM":      "quick_think_llm",
    "KUROSHIO_LLM_BACKEND_URL":      "backend_url",
    "KUROSHIO_OUTPUT_LANGUAGE":      "output_language",
    "KUROSHIO_OUTPUT_LANG":          "output_lang",
    "KUROSHIO_FUNDAMENTALS_TTL_DAYS": "fundamentals_ttl_days",
    "KUROSHIO_MAX_DEBATE_ROUNDS":    "max_debate_rounds",
    "KUROSHIO_MAX_RISK_ROUNDS":      "max_risk_discuss_rounds",
    "KUROSHIO_CHECKPOINT_ENABLED":   "checkpoint_enabled",
    "KUROSHIO_BENCHMARK_TICKER":     "benchmark_ticker",
    "KUROSHIO_MARKET_REGION":        "market_region",
    "KUROSHIO_PORTFOLIO_ROOT":       "portfolio_root",
    "KUROSHIO_TW_MARGIN_NAV_CAP":    "tw_margin_nav_cap",
    "KUROSHIO_LONG_ONLY":            "long_only",
    "KUROSHIO_TEMPERATURE":          "temperature",
    "KUROSHIO_LLM_MAX_RETRIES":      "llm_max_retries",
    # Provider-specific reasoning/thinking knobs (None = each provider's own
    # default). Settable here for non-interactive runs; the CLI also offers an
    # interactive choice, which is skipped when the matching var is set.
    "KUROSHIO_GOOGLE_THINKING_LEVEL":   "google_thinking_level",
    "KUROSHIO_OPENAI_REASONING_EFFORT": "openai_reasoning_effort",
    "KUROSHIO_ANTHROPIC_EFFORT":        "anthropic_effort",
}


_BOOL_TRUE = ("true", "1", "yes", "on")
_BOOL_FALSE = ("false", "0", "no", "off")


def _coerce(value: str, reference):
    """Coerce env-var string to the type of the existing default value.

    Invalid values raise ``ValueError`` rather than silently falling back to a
    default — a misspelled boolean (e.g. ``treu``) or non-numeric int should fail
    loudly at startup, not quietly misconfigure an unattended run.
    """
    if isinstance(reference, bool):
        normalized = value.strip().lower()
        if normalized in _BOOL_TRUE:
            return True
        if normalized in _BOOL_FALSE:
            return False
        raise ValueError(
            f"expected a boolean ({'/'.join(_BOOL_TRUE + _BOOL_FALSE)}), got {value!r}"
        )
    if isinstance(reference, int) and not isinstance(reference, bool):
        return int(value)
    if isinstance(reference, float):
        return float(value)
    return value


def _apply_env_overrides(config: dict) -> dict:
    """Apply KUROSHIO_* env vars to the config dict in-place."""
    for env_var, key in _ENV_OVERRIDES.items():
        raw = os.environ.get(env_var)
        if raw is None or raw == "":
            continue
        try:
            config[key] = _coerce(raw, config.get(key))
        except ValueError as exc:
            raise ValueError(f"Invalid value for {env_var}: {exc}") from exc
    return config


DEFAULT_CONFIG = _apply_env_overrides({
    "project_dir": os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
    "results_dir": os.getenv("KUROSHIO_RESULTS_DIR", os.path.join(_KUROSHIO_HOME, "logs")),
    "data_cache_dir": os.getenv("KUROSHIO_CACHE_DIR", os.path.join(_KUROSHIO_HOME, "cache")),
    # Kuroshio Phase 1 F1: per-ticker analyst-report cache ("facets") so a
    # daily rerun can skip analysts whose report is still fresh. See
    # graph/facet_cache.py.
    "facets_dir": os.getenv("KUROSHIO_FACETS_DIR", os.path.join(_KUROSHIO_HOME, "facets")),
    # Fundamentals are the one facet on a TTL instead of daily invalidation
    # (calendar days; keeps the free-tier Alpha Vantage quota alive).
    "fundamentals_ttl_days": 7,
    "memory_log_path": os.getenv("KUROSHIO_MEMORY_LOG_PATH", os.path.join(_KUROSHIO_HOME, "memory", "trading_memory.md")),
    # Optional cap on the number of resolved memory log entries. When set,
    # the oldest resolved entries are pruned once this limit is exceeded.
    # Pending entries are never pruned. None disables rotation entirely.
    "memory_log_max_entries": None,
    # LLM settings
    "llm_provider": "openai",
    "deep_think_llm": "gpt-5.5",
    "quick_think_llm": "gpt-5.4-mini",
    # When None, each provider's client falls back to its own default endpoint
    # (api.openai.com for OpenAI, generativelanguage.googleapis.com for Gemini, ...).
    # The CLI overrides this per provider when the user picks one. Keeping a
    # provider-specific URL here would leak (e.g. OpenAI's /v1 was previously
    # being forwarded to Gemini, producing malformed request URLs).
    "backend_url": None,
    # Provider-specific thinking configuration
    "google_thinking_level": None,      # "high", "minimal", etc.
    "openai_reasoning_effort": None,    # "medium", "high", "low"
    "anthropic_effort": None,           # "high", "medium", "low"
    # Sampling temperature, forwarded to every provider when set. None leaves
    # each provider at its own default. Lower values reduce run-to-run
    # variation on models that honor it; reasoning models largely ignore it
    # and no setting makes LLM output bit-identical across runs (see README).
    "temperature": None,
    # SDK retry budget forwarded to every provider chat client. None leaves each
    # provider/SDK at its own default (usually 2). Raise it to ride out bursty
    # 429 throttling on rate-limited deployments instead of aborting a run (#1091).
    "llm_max_retries": None,
    # Checkpoint/resume: when True, LangGraph saves state after each node
    # so a crashed run can resume from the last successful step.
    "checkpoint_enabled": False,
    # Output language for analyst reports and final decision
    # Internal agent debate stays in English for reasoning quality
    "output_language": "English",
    # Kuroshio Phase 1 F2: presentation-layer locale code (distinct from the
    # free-text `output_language` above, which applies broadly including the
    # internal debate turns). `en` is a no-op (upstream-compatible default);
    # other values look up a term glossary via agents/utils/i18n.py and are
    # applied only to analyst reports, the Research Manager's plan, the
    # Trader's proposal, and the Portfolio Manager's final decision — not the
    # Bull/Bear debate or the Aggressive/Conservative/Neutral risk discussion.
    "output_lang": "en",
    # Debate and discussion settings
    "max_debate_rounds": 1,
    "max_risk_discuss_rounds": 1,
    "max_recur_limit": 100,
    "market_region": "us",
    "default_us_tickers": ["NVDA"],
    "default_tw_tickers": ["2330.TW"],
    "default_us_analysts": ["market", "social", "news", "fundamentals"],
    "default_tw_analysts": ["market", "chip", "social", "news", "fundamentals"],
    # No default: the engine ships with no portfolio integration wired in.
    # Set KUROSHIO_PORTFOLIO_ROOT, or pass a `portfolio_state_provider` to
    # TradingAgentsGraph, to supply live NAV/positions (see graph/trading_graph.py).
    "portfolio_root": os.getenv("KUROSHIO_PORTFOLIO_ROOT"),
    # User risk knob: caps TW single-stock-futures initial margin as a fraction
    # of NAV. None means this config path applies no cap — portfolio/sizing_tw.py
    # falls back to its own conservative built-in default when unset.
    "tw_margin_nav_cap": None,
    # Long-only mandate: reframes agent ratings from absolute buy/sell to a
    # relative attractiveness ranking for capital deployment (no shorting).
    "long_only": False,
    # News / data fetching parameters
    # Increase for longer lookback strategies or to broaden macro coverage;
    # decrease to reduce token usage in agent prompts.
    "news_article_limit": 20,             # max articles per ticker (ticker-news)
    "global_news_article_limit": 10,      # max articles for global/macro news
    "global_news_lookback_days": 7,       # macro news lookback window
    # Search queries used by get_global_news for macro headlines. Extend or
    # replace to broaden geographic / sector coverage.
    "global_news_queries": [
        "Federal Reserve interest rates inflation",
        "S&P 500 earnings GDP economic outlook",
        "geopolitical risk trade war sanctions",
        "ECB Bank of England BOJ central bank policy",
        "oil commodities supply chain energy",
    ],
    # Data vendor configuration
    # Category-level configuration (default for all tools in category).
    # The configured value is the exact vendor chain — requests are NOT silently
    # routed to vendors you didn't choose. For ordered fallback, list several,
    # e.g. "yfinance,alpha_vantage". "default" uses all available vendors.
    "data_vendors": {
        "core_stock_apis": "yfinance",       # Options: alpha_vantage, yfinance
        "technical_indicators": "yfinance",  # Options: alpha_vantage, yfinance
        "fundamental_data": "yfinance",      # Options: alpha_vantage, yfinance
        "news_data": "yfinance",             # Options: alpha_vantage, yfinance
        "macro_data": "fred",                # Options: fred (needs FRED_API_KEY)
        "prediction_markets": "polymarket",  # Options: polymarket (keyless)
    },
    # Tool-level configuration (takes precedence over category-level)
    "tool_vendors": {
        # Example: "get_stock_data": "alpha_vantage",  # Override category default
    },
    # Benchmark for alpha calculation in the reflection layer.
    # ``benchmark_ticker`` (when set) overrides the suffix map for all
    # tickers; leave it None to use ``benchmark_map`` for auto-detection
    # based on the ticker's exchange suffix. SPY remains the US default
    # so the reflection label keeps reading "Alpha vs SPY" for US tickers
    # while non-US tickers get their regional index automatically.
    "benchmark_ticker": None,
    "benchmark_map": {
        ".NS":  "^NSEI",       # NSE India (Nifty 50)
        ".BO":  "^BSESN",      # BSE India (Sensex)
        ".T":   "^N225",       # Tokyo (Nikkei 225)
        ".HK":  "^HSI",        # Hong Kong (Hang Seng)
        ".L":   "^FTSE",       # London (FTSE 100)
        ".TO":  "^GSPTSE",     # Toronto (TSX Composite)
        ".AX":  "^AXJO",       # Australia (ASX 200)
        ".SS":  "000001.SS",   # Shanghai (SSE Composite)
        ".SZ":  "399001.SZ",   # Shenzhen (SZSE Component)
        "":     "SPY",         # default for US-listed tickers (no suffix)
    },
})
