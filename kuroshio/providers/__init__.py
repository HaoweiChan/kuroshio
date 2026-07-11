"""Provider registry.

Providers are optional-dependency plugins (yfinance, requests) — importing this
package must never require every vendor SDK to be installed, so each provider
module is only imported once its name is actually requested.
"""

from __future__ import annotations

import importlib

from kuroshio.providers.base import MarketDataProvider

_REGISTRY: dict[str, tuple[str, str]] = {
    "yfinance": ("kuroshio.providers.yf", "YFinanceProvider"),
    "finmind": ("kuroshio.providers.finmind", "FinMindProvider"),
}


def get_provider(name: str) -> MarketDataProvider:
    if name not in _REGISTRY:
        known = ", ".join(sorted(_REGISTRY))
        raise ValueError(f"Unknown provider {name!r}; known providers: {known}")
    module_name, class_name = _REGISTRY[name]
    module = importlib.import_module(module_name)
    return getattr(module, class_name)()
