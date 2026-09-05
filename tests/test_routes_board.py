def test_healthz(client):
    assert client.get("/healthz").json() == {"status": "healthy"}


def test_board_renders_sites_people_weather_and_flags(client):
    page = client.get("/?date=2026-07-17").text
    assert "Ada" in page and "Bo" in page
    assert "rain-risk" in page                      # outdoor site with 80% forecast
    assert "span-quote.pdf" in page and "500.00" in page  # amendment flag on Rasmus site
    assert "Depot" in page
    assert "Rasmus electrical panel overhaul" in page  # job_name headline
    assert "<th>Site needs</th><td>outdoor</td>" in page and "<th>Site needs</th><td>warehouse</td>" in page
    assert "<th>Staff needed</th><td>electrician</td>" in page
    assert "<th>Notes</th><td>SPAN panel job</td>" in page
    assert "<h2>wh " in page                        # no job name and "-" customer falls back to site_id
    assert "Crew today:" in page and "nobody assigned" in page


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
    section = page.split('sid">s9</small>')[1].split("</section>")[0]
    assert "badge unknown" in section


def test_any_site_with_coords_gets_forecast_badge(client, fakes):
    fakes["sheets"].stores["board123"]["Sites"].append(
        ["yard", "Yard", "9 Dock St", "40.70", "-74.10", "warehouse", "", ""]
    )
    page = client.get("/?date=2026-07-17").text
    section = page.split('sid">yard</small>')[1].split("</section>")[0]
    assert "badge rain-risk" in section  # 80% fake forecast applies beyond outdoor sites


def test_board_survives_broken_skipta_sheet(client, fakes):
    del fakes["sheets"].stores["skipta456"]
    page = client.get("/?date=2026-07-17")
    assert page.status_code == 200
    assert "amendment feed unavailable" in page.text.lower()


def test_board_ships_suggest_controls(client):
    page = client.get("/?date=2026-07-17").text
    assert 'id="suggest"' in page and 'id="apply"' in page
    assert "/api/v1/suggest" in page and "/api/v1/apply" in page
