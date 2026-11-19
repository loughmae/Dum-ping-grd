from datetime import date

from rotatool.schedule.patterns import parse_pattern
from rotatool.schedule.template import canonical_key, load_area_reference, derive_template


def test_pattern_simple():
    p = parse_pattern("M-F 8-4")
    assert p.fixed_days == {"Mon", "Tue", "Wed", "Thu", "Fri"}
    assert p.day_hours == 8.0 and p.weekly_hours == 40.0


def test_pattern_flexi():
    p = parse_pattern("3x 8-8")
    assert p.fixed_days is None and p.flexi_days == 3 and p.day_hours == 12.0


def test_pattern_double_t():
    assert parse_pattern("M,T,T,F").fixed_days == {"Mon", "Tue", "Thu", "Fri"}
    assert parse_pattern("T,W,T").fixed_days == {"Tue", "Wed", "Thu"}


def test_pattern_single_t_with_w():
    assert parse_pattern("W,T,F").fixed_days == {"Wed", "Thu", "Fri"}


def test_pattern_half_hour_start():
    p = parse_pattern("W-F (7:30-8)")
    assert p.fixed_days == {"Wed", "Thu", "Fri"} and p.day_hours == 12.5


def test_pattern_alternating_weeks():
    p = parse_pattern("Wk1/2 T(8-8),W(8-4),F(8-6).Wk3/4 M(8-8) T(8-6) W(8-4)")
    assert p.fixed_days is None and p.flexi_days == 3


def test_pattern_empty():
    p = parse_pattern("")
    assert p.fixed_days is None and p.flexi_days == 5
