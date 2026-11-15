"""The statistics of preclinical.tox_study_monitor (pre-registered in
docs/preclinical-eval.md). Pure functions of numbers; each is tested against a published
or hand-computed example (tests/unit/test_tox_stats.py).

- dunnett: many-to-one comparison of each dose group with the control (scipy.stats.dunnett,
  two-sided; its multivariate t integration seeded, so a result is reproducible).
- jonckheere: Jonckheere-Terpstra test for ordered alternatives (Hollander and Wolfe,
  Nonparametric Statistical Methods, 3rd ed., section 6.2), normal approximation with the
  tie correction, two-sided.
- cochran_armitage: trend in proportions (Agresti, Categorical Data Analysis, 2nd ed.,
  section 5.3.5), one-sided for an increase.
- fisher_greater: Fisher's exact test of a dose group against control, one-sided for a
  higher incidence (scipy.stats.fisher_exact).
"""

import math
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from scipy import stats


@dataclass(frozen=True, slots=True)
class TrendResult:
    statistic: float
    z: float
    p: float


def dunnett(control: Sequence[float], groups: Sequence[Sequence[float]], seed: int) -> list[float]:
    """Two-sided Dunnett p-value of each group against control, in the given order."""
    if not groups:
        return []
    result = stats.dunnett(
        *[np.asarray(g, dtype=float) for g in groups],
        control=np.asarray(control, dtype=float),
        alternative="two-sided",
        rng=np.random.default_rng(seed),
    )
    return [float(min(1.0, max(0.0, p))) for p in result.pvalue]


def jonckheere(groups: Sequence[Sequence[float]]) -> TrendResult:
    """Jonckheere-Terpstra J for groups in their order (control first), its z and the
    two-sided p from the normal approximation with the tie correction."""
    sizes = [len(g) for g in groups]
    n = sum(sizes)
    j = 0.0
    for i, lower in enumerate(groups):
        for upper in groups[i + 1 :]:
            for a in lower:
                for b in upper:
                    j += 1.0 if b > a else 0.5 if b == a else 0.0
    mean = (n * n - sum(s * s for s in sizes)) / 4.0
    ties = list(Counter(v for g in groups for v in g).values())
    var = (
        n * (n - 1) * (2 * n + 5)
        - sum(s * (s - 1) * (2 * s + 5) for s in sizes)
        - sum(t * (t - 1) * (2 * t + 5) for t in ties)
    ) / 72.0
    if n > 2:
        var += (
            sum(s * (s - 1) * (s - 2) for s in sizes) * sum(t * (t - 1) * (t - 2) for t in ties)
        ) / (36.0 * n * (n - 1) * (n - 2))
    if n > 1:
        var += (sum(s * (s - 1) for s in sizes) * sum(t * (t - 1) for t in ties)) / (
            8.0 * n * (n - 1)
        )
    if var <= 0:
        return TrendResult(statistic=j, z=0.0, p=1.0)
    z = (j - mean) / math.sqrt(var)
    return TrendResult(statistic=j, z=z, p=float(2 * stats.norm.sf(abs(z))))


def cochran_armitage(
    affected: Sequence[int], totals: Sequence[int], scores: Sequence[float]
) -> TrendResult:
    """Cochran-Armitage trend z and the one-sided p for incidence rising with the scores."""
    n = sum(totals)
    if n == 0:
        return TrendResult(statistic=0.0, z=0.0, p=1.0)
    p_bar = sum(affected) / n
    t = sum(s * (x - m * p_bar) for s, x, m in zip(scores, affected, totals, strict=True))
    s1 = sum(m * s for m, s in zip(totals, scores, strict=True))
    s2 = sum(m * s * s for m, s in zip(totals, scores, strict=True))
    var = p_bar * (1 - p_bar) * (s2 - s1 * s1 / n)
    if var <= 0:
        return TrendResult(statistic=t, z=0.0, p=1.0)
    z = t / math.sqrt(var)
    return TrendResult(statistic=t, z=z, p=float(stats.norm.sf(z)))


def fisher_greater(affected: int, total: int, control_affected: int, control_total: int) -> float:
    """One-sided Fisher exact p that the group's incidence exceeds the control's."""
    table = [[affected, total - affected], [control_affected, control_total - control_affected]]
    return float(stats.fisher_exact(table, alternative="greater").pvalue)
