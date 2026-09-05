from app.board import read_assignments, read_condition_override, read_crews, read_sites
from tests.fakes import FakeSheets

BOARD = "board123"


def make_sheets():
    return FakeSheets({
        BOARD: {
            "Crews": [
                ["p1", "Ada", "electrician, apprentice", "alpha"],
                ["p2", "Bo", "hvac", "alpha"],
                ["p3", "Cy"],  # short row: no crafts, no crew
            ],
            "Sites": [
                ["s1", "Smith", "1 Main St", "40.79", "-74.25", "outdoor", "electrician", "panel job"],
                ["s2", "Jones", "2 Oak Ave", "", "", "indoor", "", ""],
                ["s3", "Reyes", "3 Elm Rd", "40.79°N", "-74.25", "outdoor", "", ""],  # hand-typed coord
                ["wh", "—", "Depot", "", "", "warehouse", "", ""],
            ],
            "Assignments": [
                ["2026-07-16", "p1", "s1", ""],
                ["2026-07-16", "p2", "s2", "second fix"],
                ["2026-07-17", "p1", "wh", ""],
            ],
            "Days": [["2026-07-17", "rain", "forecast said so"]],
        }
    })


def test_read_crews_parses_crafts_and_pads():
    crews = read_crews(make_sheets(), BOARD)
    assert crews[0]["crafts"] == ["electrician", "apprentice"]
    assert crews[2] == {"person_id": "p3", "name": "Cy", "crafts": [], "crew": ""}


def test_read_sites_parses_coords_and_lists():
    sites = read_sites(make_sheets(), BOARD)
    assert sites[0]["lat"] == 40.79 and sites[0]["lon"] == -74.25
    assert sites[0]["needed_crafts"] == ["electrician"]
    assert sites[1]["lat"] is None and sites[1]["needed_crafts"] == []
    assert sites[2]["lat"] is None and sites[2]["lon"] == -74.25  # unparseable coord degrades, not 500s
    assert sites[3]["work_type"] == "warehouse"


def test_non_finite_coords_degrade_to_none():
    sheets = FakeSheets({BOARD: {"Sites": [["s4", "X", "addr", "nan", "inf", "outdoor", "", ""]]}})
    sites = read_sites(sheets, BOARD)
    assert sites[0]["lat"] is None and sites[0]["lon"] is None


def test_read_assignments_filters_by_date_with_rows():
    got = read_assignments(make_sheets(), BOARD, "2026-07-16")
    assert [(a["row"], a["person_id"], a["site_id"]) for a in got] == [(2, "p1", "s1"), (3, "p2", "s2")]


def test_condition_override_hit_and_miss():
    sheets = make_sheets()
    assert read_condition_override(sheets, BOARD, "2026-07-17") == "rain"
    assert read_condition_override(sheets, BOARD, "2026-07-16") == ""
