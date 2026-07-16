from app.weather import fetch_precip_probability, resolve_condition

FORECAST = {"daily": {"precipitation_probability_max": [70]}}


def test_fetch_parses_probability_and_builds_url():
    seen = {}

    def fake_get(url):
        seen["url"] = url
        return FORECAST

    assert fetch_precip_probability(fake_get, 40.79, -74.25, "2026-07-17") == 70
    assert "latitude=40.79" in seen["url"] and "start_date=2026-07-17" in seen["url"]


def test_fetch_soft_fails_to_none():
    def boom(url):
        raise RuntimeError("offline")

    assert fetch_precip_probability(boom, 1.0, 2.0, "2026-07-17") is None
    assert fetch_precip_probability(lambda url: {"daily": {}}, 1.0, 2.0, "2026-07-17") is None


def test_resolve_condition_order():
    assert resolve_condition("rain", 0, 50) == "rain"  # override wins
    assert resolve_condition("", None, 50) == "unknown"
    assert resolve_condition("", 70, 50) == "rain-risk"
    assert resolve_condition("", 30, 50) == "clear"
