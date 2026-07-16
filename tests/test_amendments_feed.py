from datetime import date

from app.amendments_feed import read_amendment_flags
from tests.fakes import FakeSheets

SKIPTA = "skipta456"
SITES = [
    {"site_id": "s1", "customer_name": "Smith"},
    {"site_id": "s2", "customer_name": "Rasmus"},
]


def row(customer, total, status, signed_at, kind, proposal):
    return ["aid", "c", customer, "v", "{}", "[]", total, status, "url", signed_at, kind, "fid", proposal, "", "", ""]


def make_sheets(rows):
    return FakeSheets({SKIPTA: {"Amendments": rows}})


def test_flags_signed_amend_rows_matched_to_sites():
    sheets = make_sheets([
        row("rasmus", "500.00", "signed", "2026-07-14T10:00:00+00:00", "amend", "span-quote.pdf"),
        row("Smith", "99.00", "draft", "", "amend", "x.pdf"),          # not signed
        row("Smith", "50.00", "signed", "2026-07-14T10:00:00+00:00", "new", ""),  # not an amendment
        row("Nobody", "1.00", "signed", "2026-07-14T10:00:00+00:00", "amend", "y.pdf"),  # no site
    ])
    flags = read_amendment_flags(sheets, SKIPTA, SITES, date(2026, 7, 15), 14)
    assert flags == {"s2": [{"proposal_name": "span-quote.pdf", "total": 500.00}]}


def test_lookback_window_excludes_old_rows():
    sheets = make_sheets([row("Smith", "10.00", "signed", "2026-06-01T00:00:00+00:00", "amend", "old.pdf")])
    assert read_amendment_flags(sheets, SKIPTA, SITES, date(2026, 7, 15), 14) == {}


def test_short_and_dateless_rows_are_skipped():
    sheets = make_sheets([["aid", "c", "Smith", "v", "{}", "[]", "5.00", "signed"], row("Smith", "5.00", "signed", "", "amend", "z.pdf")])
    assert read_amendment_flags(sheets, SKIPTA, SITES, date(2026, 7, 15), 14) == {}
