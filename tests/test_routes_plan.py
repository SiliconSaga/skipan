from app.planner import PlanError


def test_suggest_returns_verified_plan_without_writing(client, fakes):
    resp = client.post("/api/v1/suggest", json={"date": "2026-07-17"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["summary"] == "Move Ada to the depot."
    assert data["moves"][0]["valid"] is True and data["moves"][0]["to_site"] == "wh"
    assert data["warnings"] == ["s1: missing craft(s) electrician"]
    rows = fakes["sheets"].stores["board123"]["Assignments"]
    assert ["2026-07-17", "p1", "s1", ""] in rows  # unchanged — suggest never writes


def test_suggest_flags_hallucinated_person(client, fakes):
    fakes["plan"] = fakes["plan"].model_copy(update={"moves": [
        {"person_id": "ghost", "from_site": "", "to_site": "wh", "reason": "x"}
    ]})
    data = client.post("/api/v1/suggest", json={"date": "2026-07-17"}).json()
    assert data["moves"][0]["valid"] is False


def test_apply_moves_and_reject_invalid(client, fakes):
    ok = client.post("/api/v1/apply", json={"date": "2026-07-17", "moves": [
        {"person_id": "p1", "from_site": "s1", "to_site": "wh"}
    ]})
    assert ok.status_code == 200 and ok.json()["applied"] == 1
    rows = fakes["sheets"].stores["board123"]["Assignments"]
    assert ["2026-07-17", "p1", "wh", ""] in rows
    bad = client.post("/api/v1/apply", json={"date": "2026-07-17", "moves": [
        {"person_id": "p1", "from_site": "s1", "to_site": "wh"}  # stale from_site now
    ]})
    assert bad.status_code == 422


def test_planner_failure_is_502(client, fakes, monkeypatch):
    def boom(context, settings):
        raise PlanError("all models failed")

    from app.main import app, get_plan
    app.dependency_overrides[get_plan] = lambda: boom
    resp = client.post("/api/v1/suggest", json={"date": "2026-07-17"})
    assert resp.status_code == 502
