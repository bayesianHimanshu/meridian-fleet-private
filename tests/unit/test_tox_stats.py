"""Each method of preclinical.tox_study_monitor against a published or hand-computed
example (phase 5 step 1, docs/preclinical-eval.md)."""

import itertools
import math
import statistics

import pytest

from meridian.preclinical.stats import cochran_armitage, dunnett, fisher_greater, jonckheere


def test_dunnett_reproduces_dunnetts_1955_example() -> None:
    # Dunnett CW. A multiple comparison procedure for comparing several treatments with a
    # control. J Am Stat Assoc 1955;50:1096-1121: blood counts (millions per cubic mm),
    # control and two drugs. t = 0.86 (A) and 3.69 (B); B differs at the 1% level.
    control = [7.40, 8.50, 7.20, 8.24, 9.84, 8.32]
    drug_a = [9.76, 8.80, 7.68, 9.36]
    drug_b = [12.80, 9.68, 12.16, 9.20, 10.55]
    p = dunnett(control, [drug_a, drug_b], seed=20261115)
    assert p[0] == pytest.approx(0.620, abs=0.005)
    assert p[1] == pytest.approx(0.0058, abs=0.0005)
    assert p[1] < 0.01 < p[0]
    assert p == dunnett(control, [drug_a, drug_b], seed=20261115)  # seeded: reproducible


def test_jonckheere_hand_computed_without_ties() -> None:
    # Groups (1, 2), (3), (4, 5): every later value exceeds every earlier one, J = 8.
    # E(J) = (N^2 - sum n^2) / 4 = (25 - 9) / 4 = 4.
    # Var(J) = (N^2 (2N + 3) - sum n^2 (2n + 3)) / 72 = (325 - 61) / 72 = 3.6667.
    r = jonckheere([[1, 2], [3], [4, 5]])
    assert r.statistic == 8
    assert r.z == pytest.approx(4 / math.sqrt(264 / 72))
    assert r.p == pytest.approx(0.0367, abs=0.0005)


def test_jonckheere_hand_computed_with_ties() -> None:
    # Groups (1, 1), (1, 2): pairs (1,1) count 0.5, (1,2) count 1: J = 3, E(J) = 2.
    # Tie-corrected variance, ties t = (3, 1): (156 - 36 - 66) / 72 + 0 + (4 * 6) / 96 = 1.
    r = jonckheere([[1, 1], [1, 2]])
    assert r.statistic == 3
    assert r.z == pytest.approx(1.0)
    assert r.p == pytest.approx(0.3173, abs=0.0005)


@pytest.mark.parametrize("data", [[[1, 2], [3], [4, 5]], [[1, 1], [1, 2]], [[2, 1, 2], [2, 3]]])
def test_jonckheere_variance_equals_the_permutation_variance(
    data: list[list[float]],
) -> None:
    # Under the null every assignment of the values to the groups is equally likely; the
    # variance of J over all assignments is the variance the formula gives.
    values = [v for g in data for v in g]
    sizes = [len(g) for g in data]
    js = []
    for perm in itertools.permutations(values):
        groups, start = [], 0
        for s in sizes:
            groups.append(list(perm[start : start + s]))
            start += s
        js.append(jonckheere(groups).statistic)
    observed = jonckheere(data)
    exact_var = statistics.pvariance(js)
    mean = statistics.fmean(js)
    if exact_var > 0:
        assert observed.z == pytest.approx((observed.statistic - mean) / math.sqrt(exact_var))


def test_cochran_armitage_reproduces_agrestis_alcohol_example() -> None:
    # Agresti, Categorical Data Analysis (2002), Table 2.7 and section 3.4.6: infant
    # malformation by maternal alcohol consumption, scores 0, 0.5, 1.5, 4, 7.
    # The trend statistic is z = 2.56 (M^2 = 6.57), one-sided P = 0.005.
    present = [48, 38, 5, 1, 1]
    absent = [17066, 14464, 788, 126, 37]
    totals = [p + a for p, a in zip(present, absent, strict=True)]
    r = cochran_armitage(present, totals, [0, 0.5, 1.5, 4.0, 7.0])
    assert r.z == pytest.approx(2.56, abs=0.01)
    assert r.p == pytest.approx(0.005, abs=0.0005)


def test_cochran_armitage_hand_computed() -> None:
    # 0/10, 0/10, 3/10, 8/10, scores 0..3: p = 11/40, T = sum s x - p sum n s = 30 - 16.5,
    # Var = p (1 - p) (sum n s^2 - (sum n s)^2 / N) = 0.199375 * (140 - 90) = 9.96875.
    r = cochran_armitage([0, 0, 3, 8], [10, 10, 10, 10], [0, 1, 2, 3])
    assert r.statistic == pytest.approx(13.5)
    assert r.z == pytest.approx(13.5 / math.sqrt(9.96875))
    assert r.p < 0.05


def test_no_variation_gives_no_trend() -> None:
    assert cochran_armitage([0, 0, 0], [10, 10, 10], [0, 1, 2]).p == 1.0
    assert jonckheere([[1.0, 1.0], [1.0, 1.0]]).p == 1.0


def test_fisher_reproduces_the_tea_tasting_experiment() -> None:
    # Fisher (1935): 3 of 4 milk-first cups named correctly; one-sided P = 17/70.
    assert fisher_greater(3, 4, 1, 4) == pytest.approx(17 / 70)
    # 5 of 10 against 0 of 10: P = C(10,5) C(10,0) / C(20,5) summed upward = 0.0163.
    assert fisher_greater(5, 10, 0, 10) == pytest.approx(0.01625, abs=0.0001)
