"""Wilson score confidence intervals for binomial proportions, and small formatting
helpers shared by the audit recompute and the reports.

Every published rate in this project is a binomial proportion (k successes of n), so a
Wilson score interval is the right small-sample interval: it stays inside [0, 1], is
defined at k = 0 and k = n, and does not assume the normal approximation the way a Wald
interval does. z = 1.96 is the two-sided 95% level.

Recall is deliberately NOT run through this: it is a mean of per-question recall fractions,
not a single binomial proportion, so a Wilson interval would misdescribe it.
"""
from __future__ import annotations

import math

Z95 = 1.959963984540054  # two-sided 95%


def wilson_interval(successes: int, total: int, z: float = Z95) -> tuple[float, float] | None:
    """The Wilson score interval (lo, hi) for `successes` of `total`, clamped to [0, 1].
    None when total is 0 (the rate itself is undefined)."""
    if total <= 0:
        return None
    n = float(total)
    p = successes / n
    z2 = z * z
    denom = 1.0 + z2 / n
    center = (p + z2 / (2.0 * n)) / denom
    margin = (z * math.sqrt(p * (1.0 - p) / n + z2 / (4.0 * n * n))) / denom
    lo = center - margin
    hi = center + margin
    return (max(0.0, lo), min(1.0, hi))


def rate_with_ci(successes: int, total: int, z: float = Z95) -> dict:
    """Machine-readable rate: numerator, denominator, point estimate, and 95% Wilson
    interval, each rounded to 4 places. rate and ci95 are None when total is 0."""
    ci = wilson_interval(successes, total, z)
    return {
        "num": successes,
        "den": total,
        "rate": None if total <= 0 else round(successes / total, 4),
        "ci95": None if ci is None else [round(ci[0], 4), round(ci[1], 4)],
    }


def fmt_pct_ci(successes: int, total: int, z: float = Z95) -> str:
    """Human-facing rate: '93.3% (166/178, 95% CI 88.6-96.3%)'. 'n/a' when total is 0."""
    if total <= 0:
        return "n/a"
    ci = wilson_interval(successes, total, z)
    p = 100.0 * successes / total
    return f"{p:.1f}% ({successes}/{total}, 95% CI {100 * ci[0]:.1f}-{100 * ci[1]:.1f}%)"
