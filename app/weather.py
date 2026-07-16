"""open-meteo daily forecast (keyless) with soft failure; overrides always win."""
import logging

OPEN_METEO_URL = (
    "https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
    "&daily=precipitation_probability_max&timezone=auto&start_date={date}&end_date={date}"
)

logger = logging.getLogger("skipan.weather")


def default_http_get_json(url: str) -> dict:
    import httpx

    response = httpx.get(url, timeout=5.0)
    response.raise_for_status()
    return response.json()


def fetch_precip_probability(http_get_json, lat: float, lon: float, date: str):
    try:
        data = http_get_json(OPEN_METEO_URL.format(lat=lat, lon=lon, date=date))
        return int(data["daily"]["precipitation_probability_max"][0])
    except Exception as exc:  # weather is an enrichment — never take the board down
        logger.warning("forecast unavailable for %s,%s on %s: %s", lat, lon, date, exc)
        return None


def resolve_condition(override: str, precip, threshold: int) -> str:
    if override:
        return override
    if precip is None:
        return "unknown"
    return "rain-risk" if precip >= threshold else "clear"
