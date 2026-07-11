"""Presentation-layer output-language directive — Kuroshio Phase 1 F2.

Distinct from the pre-existing ``get_language_instruction()`` in
``agent_utils.py`` (driven by the free-text ``output_language`` config key,
"English"/"Spanish"/... and applied everywhere including the internal
Bull/Bear and risk-discussion debate turns). ``lang_directive`` is driven by
the locale-code ``output_lang`` key (``"en"`` / ``"zh-TW"``) and is only
wired into the nodes whose output actually reaches the user: the five
analysts, the Research Manager's investment plan, the Trader's proposal, and
the Portfolio Manager's final decision. It is deliberately NOT added to
``bull_researcher.py`` / ``bear_researcher.py`` / the three risk debators —
that internal debate stays English for reasoning quality and token cost.

``output_language`` stays at its default ("English", a no-op) for a
Kuroshio zh-TW run, so the two directives never collide — this module is
purely additive.
"""

from __future__ import annotations

import functools
from pathlib import Path

import yaml

_CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config" / "i18n"


@functools.lru_cache(maxsize=8)
def _load_glossary(lang: str) -> dict[str, str]:
    path = _CONFIG_DIR / f"{lang}.yaml"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return {str(k): str(v) for k, v in data.items()}


def lang_directive() -> str:
    """Prompt-tail instruction for ``config['output_lang']``.

    Empty string for ``"en"`` (default, upstream-compatible, no extra
    tokens). For a language with a glossary file (currently ``zh-TW``),
    appends the curated term mapping. A locale with no glossary file falls
    back to a plain "write in <lang>" instruction.
    """
    from kuroshio.agents.engine.dataflows.config import get_config

    lang = str(get_config().get("output_lang", "en") or "en").strip()
    if lang.lower() == "en":
        return ""
    glossary = _load_glossary(lang)
    if not glossary:
        return f" Write your entire response in {lang}."
    terms = "; ".join(f"{en}={local}" for en, local in glossary.items())
    return (
        f" Write your entire response in {lang}. Use these term translations "
        f"consistently: {terms}. When stating a final rating, always include "
        f"the English rating word (Buy/Overweight/Hold/Underweight/Sell) "
        f"alongside the translation, e.g. 評等：加碼 (Overweight)."
    )
