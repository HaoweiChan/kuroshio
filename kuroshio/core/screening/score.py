"""Cross-sectional scoring utilities shared by every market profile.

Ported from the maintainer's production TW screener (``_pctrank``) — the TW
and US profiles both rank their raw factors with this same function, so
scores are comparable in shape (not magnitude) across markets.
"""

from __future__ import annotations

from typing import Sequence


def pctrank(values: Sequence[float]) -> list[float]:
    """Cross-sectional percentile rank in [0, 1] with average-rank tie handling.

    ``pctrank = rank / (n - 1)``. For n <= 1 (a lone passer) returns 0.0 — there is
    no cross-section to rank against.
    """
    n = len(values)
    if n <= 1:
        return [0.0] * n
    order = sorted(range(n), key=lambda i: values[i])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg / (n - 1)
        i = j + 1
    return ranks


def weighted_score(scores: dict[str, float], weights: dict[str, float]) -> float:
    """Weighted sum of ``scores``, renormalizing ``weights`` over the keys present
    in ``scores`` — the graceful-degradation rule: a factor with no data drops out
    instead of being faked, and the remaining weights pick up its share."""
    present = {k: w for k, w in weights.items() if k in scores}
    total = sum(present.values())
    if total <= 0:
        return 0.0
    return sum(scores[k] * w / total for k, w in present.items())
