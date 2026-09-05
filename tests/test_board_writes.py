from app.board import apply_moves, read_assignments, read_condition_override, set_condition
from tests.fakes import FakeSheets

BOARD = "board123"


def make_sheets():
    return FakeSheets({
        BOARD: {
            "Assignments": [
                ["2026-07-16", "p1", "s1", ""],
                ["2026-07-16", "p2", "s2", "keep note"],
            ],
            "Days": [["2026-07-16", "", ""]],
        }
    })


def test_apply_moves_updates_existing_row_preserving_note():
    sheets = make_sheets()
    applied = apply_moves(sheets, BOARD, "2026-07-16", [{"person_id": "p2", "to_site": "wh"}])
    assert applied == 1
    got = {a["person_id"]: a for a in read_assignments(sheets, BOARD, "2026-07-16")}
    assert got["p2"]["site_id"] == "wh" and got["p2"]["note"] == "keep note"


def test_apply_moves_appends_for_unassigned_person():
    sheets = make_sheets()
    apply_moves(sheets, BOARD, "2026-07-16", [{"person_id": "p9", "to_site": "s1"}])
    got = {a["person_id"]: a["site_id"] for a in read_assignments(sheets, BOARD, "2026-07-16")}
    assert got["p9"] == "s1"


def test_reads_and_updates_retry_but_appends_never_do():
    sheets = make_sheets()
    apply_moves(sheets, BOARD, "2026-07-16", [{"person_id": "p2", "to_site": "wh"}, {"person_id": "p9", "to_site": "s1"}])
    calls = sheets.values().calls
    assert ("update", 2) in calls and ("append", 0) in calls
    assert all(retries == 2 for verb, retries in calls if verb in ("get", "update"))
    assert all(retries == 0 for verb, retries in calls if verb == "append")  # a retried append can duplicate rows


def test_set_condition_updates_then_appends():
    sheets = make_sheets()
    set_condition(sheets, BOARD, "2026-07-16", "rain")
    assert read_condition_override(sheets, BOARD, "2026-07-16") == "rain"
    set_condition(sheets, BOARD, "2026-07-18", "clear")
    assert read_condition_override(sheets, BOARD, "2026-07-18") == "clear"
