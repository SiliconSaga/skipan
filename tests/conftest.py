import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import app, get_http_get_json, get_plan, get_settings, get_sheets
from app.planner import Plan
from tests.fakes import FakeSheets

BOARD = "board123"
SKIPTA = "skipta456"
TODAY = "2026-07-17"


def seed_stores():
    return {
        BOARD: {
            "Crews": [
                ["p1", "Ada", "electrician", "alpha"],
                ["p2", "Bo", "hvac", "alpha"],
                ["p3", "Cy", "apprentice", "beta"],
            ],
            "Sites": [
                ["s1", "Rasmus", "1 Main St", "40.79", "-74.25", "outdoor", "electrician", ""],
                ["s2", "Jones", "2 Oak Ave", "", "", "indoor", "", ""],
                ["wh", "-", "Depot", "", "", "warehouse", "", ""],
            ],
            "Assignments": [
                [TODAY, "p1", "s1", ""],
                [TODAY, "p2", "s2", ""],
            ],
            "Days": [],
        },
        SKIPTA: {
            "Amendments": [
                ["aid", "c", "Rasmus", "v", "{}", "[]", "500.00", "signed", "url",
                 "2026-07-15T10:00:00+00:00", "amend", "fid", "span-quote.pdf", "", "", ""],
            ]
        },
    }


@pytest.fixture
def fakes():
    return {
        "sheets": FakeSheets(seed_stores()),
        "forecast": {"daily": {"precipitation_probability_max": [80]}},
        "plan": Plan.model_validate(
            {"moves": [{"person_id": "p1", "from_site": "s1", "to_site": "wh", "reason": "rain risk"}],
             "summary": "Move Ada to the depot."}
        ),
    }


@pytest.fixture
def client(fakes):
    app.dependency_overrides[get_settings] = lambda: Settings(
        project_id="p", region="r", board_sheet_id=BOARD, skipta_sheet_id=SKIPTA, base_url="http://testserver",
        model_names=["fake"], max_output_tokens=64, rate_limit_per_minute=1000, rain_threshold=50, lookback_days=14,
    )
    app.dependency_overrides[get_sheets] = lambda: fakes["sheets"]
    app.dependency_overrides[get_http_get_json] = lambda: (lambda url: fakes["forecast"])
    app.dependency_overrides[get_plan] = lambda: (lambda context, settings: fakes["plan"])
    # The limiter's limit-lambda calls get_settings() directly, outside Depends resolution,
    # so dependency_overrides can't reach it — the suite would share one real 10/min budget.
    app.state.limiter.enabled = False
    client = TestClient(app)
    client.fakes = fakes
    yield client
    app.state.limiter.enabled = True
    app.dependency_overrides.clear()
