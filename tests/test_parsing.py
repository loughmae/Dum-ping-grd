from rotatool.parsing.names import resolve, resolve_cell, split_cell
from rotatool.parsing.rota_workbook import classify, parse_date_cell


def test_split_cell_multi_and_slash():
    assert split_cell("Kitija/Jen") == ["Kitija", "Jen"]


def test_resolve_extracts_time_and_resolves():
    staff = ["Salim", "Carlo", "Kitija", "Jennila", "Jenner", "Markpol"]
    e = resolve("Salim8-6", staff)
    assert e.resolved and e.person == "Salim"
    assert e.explicit_time == "8-6"


def test_resolve_late_flag():
    e = resolve("Carlo(L)", ["Carlo"])
    assert e.resolved and e.person == "Carlo" and e.late


def test_resolve_typo():
    e = resolve("Kitjia", ["Kitija", "Carlo"])
    assert e.resolved and e.person == "Kitija"


def test_resolve_ambiguous_prefix():
    e = resolve("Jen", ["Jennila", "Jenner"])
    assert not e.resolved and set(e.candidates) == {"Jennila", "Jenner"}


def test_resolve_alias():
    e = resolve("Jhon", ["Johnrey"])
    assert e.resolved and e.person == "Johnrey"


def test_resolve_cell_multiple():
    entries = resolve_cell("Gladys/Jhon", ["Gladys", "Johnrey"])
    assert [x.person for x in entries] == ["Gladys", "Johnrey"]


def test_parse_date_cell():
    d = parse_date_cell("Mon 5th May", 2025)
    assert d.isoformat() == "2025-05-05"
    assert parse_date_cell("no date here", 2025) is None


def test_classify():
    assert classify("Absent: 3") == "absence"
    assert classify("COMMENTS:") == "comment"
    assert classify("Staff: 12") == "staff_ref"
    assert classify("Bank Staff: 2") == "bank"
    assert classify("Cath Lab : Early 1") == "area"
    assert classify("") == "empty"
