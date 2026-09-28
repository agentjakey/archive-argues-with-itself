"""Wilson score interval tests: known values, edge cases, and invariants."""
from __future__ import annotations

from archive_debugger.eval.stats import fmt_pct_ci, rate_with_ci, wilson_interval


def test_undefined_when_no_trials():
    assert wilson_interval(0, 0) is None
    assert rate_with_ci(0, 0)["rate"] is None
    assert rate_with_ci(0, 0)["ci95"] is None
    assert fmt_pct_ci(0, 0) == "n/a"


def test_known_half():
    # 50/100 Wilson 95% is approximately (0.4038, 0.5962).
    lo, hi = wilson_interval(50, 100)
    assert abs(lo - 0.4038) < 0.001
    assert abs(hi - 0.5962) < 0.001


def test_known_pilot_strict_support():
    # 166/178 (the published strict citation-support rate) -> about (0.886, 0.961).
    lo, hi = wilson_interval(166, 178)
    assert 0.88 < lo < 0.89
    assert 0.95 < hi < 0.97


def test_all_successes_upper_bound_is_one():
    lo, hi = wilson_interval(1, 1)
    assert hi == 1.0
    assert 0.0 < lo < 1.0
    lo2, hi2 = wilson_interval(119, 119)
    assert hi2 == 1.0
    assert lo2 > 0.95   # 119/119 has a tight, high lower bound


def test_zero_successes_lower_bound_is_zero():
    lo, hi = wilson_interval(0, 35)
    assert lo < 1e-9         # zero to machine precision (rounds to 0.0 in reports)
    assert 0.0 < hi < 0.15   # 0/35 upper bound is small but not zero
    assert rate_with_ci(0, 35)["ci95"][0] == 0.0   # rounded output is exactly 0.0


def test_interval_contains_point_and_stays_in_unit():
    for k, n in [(1, 3), (7, 10), (298, 304), (5, 15), (2, 7), (166, 178)]:
        lo, hi = wilson_interval(k, n)
        p = k / n
        assert 0.0 <= lo <= p <= hi <= 1.0


def test_more_trials_narrow_the_interval():
    lo_small, hi_small = wilson_interval(9, 10)
    lo_big, hi_big = wilson_interval(90, 100)   # same rate, ten times the data
    assert (hi_big - lo_big) < (hi_small - lo_small)


def test_rate_with_ci_shape():
    r = rate_with_ci(166, 178)
    assert r["num"] == 166 and r["den"] == 178
    assert abs(r["rate"] - 0.9326) < 0.0005
    assert len(r["ci95"]) == 2 and r["ci95"][0] < r["rate"] < r["ci95"][1]


def test_fmt_contains_point_and_interval():
    s = fmt_pct_ci(166, 178)
    assert "93.3%" in s and "166/178" in s and "95% CI" in s
