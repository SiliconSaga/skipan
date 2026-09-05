def test_healthz(client):
    assert client.get("/healthz").json() == {"status": "healthy"}


def test_board_renders_sites_people_weather_and_flags(client):
    page = client.get("/?date=2026-07-17").text
    assert "Ada" in page and "Bo" in page
    assert "rain-risk" in page                      # outdoor site with 80% forecast
    assert "span-quote.pdf" in page and "500.00" in page  # amendment flag on Rasmus site
    assert "Depot" in page


def test_condition_override_wins_on_next_render(client):
    resp = client.post("/api/v1/condition", json={"date": "2026-07-17", "condition": "clear"})
    assert resp.status_code == 200
    page = client.get("/?date=2026-07-17").text
    assert "rain-risk" not in page


def test_coordless_outdoor_site_shows_unknown_badge(client, fakes):
    fakes["sheets"].stores["board123"]["Sites"].append(
        ["s9", "Reyes", "9 Elm Rd", "", "", "outdoor", "", ""]
    )
    page = client.get("/?date=2026-07-17").text
    section = page.split("s9 — Reyes")[1].split("</section>")[0]
    assert "badge unknown" in section


def test_board_survives_broken_skipta_sheet(client, fakes):
    del fakes["sheets"].stores["skipta456"]
    page = client.get("/?date=2026-07-17")
    assert page.status_code == 200
    assert "amendment feed unavailable" in page.text.lower()


def test_board_ships_suggest_controls(client):
    page = client.get("/?date=2026-07-17").text
    assert 'id="suggest"' in page and 'id="apply"' in page
    assert "/api/v1/suggest" in page and "/api/v1/apply" in page
