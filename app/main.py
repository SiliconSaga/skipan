"""Skipan — crew board. Routes only; logic lives in the sibling modules."""
import logging
import os
import threading
from datetime import date as date_type
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, field_validator
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app import amendments_feed, board, planner, verifier, weather
from app.config import Settings
from app.google_clients import build_sheets, get_credentials, make_model_factory

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper(), format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("skipan")

app = FastAPI(title="Skipan")
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

limiter = Limiter(key_func=get_remote_address, default_limits=[])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

_settings: Settings | None = None
_local = threading.local()


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings.from_env()
    return _settings


def get_sheets():
    # One client per thread: httplib2 under googleapiclient is not thread-safe, and endpoints run
    # in a threadpool — a shared client's stale TLS connection surfaces as ssl.SSLError 500s.
    if not hasattr(_local, "sheets"):
        _local.sheets = build_sheets(get_credentials())
    return _local.sheets


def get_http_get_json():
    return weather.default_http_get_json


def get_plan():
    def _plan(context: dict, settings: Settings):
        factory = make_model_factory(settings.project_id, settings.region)
        return planner.suggest_plan(
            context, model_factory=factory, model_names=settings.model_names, max_output_tokens=settings.max_output_tokens
        )

    return _plan


def _valid_date(value: str) -> str:
    try:
        return date_type.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"bad date {value!r} — want YYYY-MM-DD") from exc


def _load_day(settings: Settings, sheets, http_get_json, date: str) -> dict:
    crews = board.read_crews(sheets, settings.board_sheet_id)
    sites = board.read_sites(sheets, settings.board_sheet_id)
    for site in sites:
        site["display"] = board.display_name(site)
    assignments = board.read_assignments(sheets, settings.board_sheet_id, date)
    override = board.read_condition_override(sheets, settings.board_sheet_id, date)
    conditions = {}
    for site in sites:
        has_coords = site["lat"] is not None and site["lon"] is not None
        if has_coords:
            precip = weather.fetch_precip_probability(http_get_json, site["lat"], site["lon"], date)
            conditions[site["site_id"]] = weather.resolve_condition(override, precip, settings.rain_threshold)
        elif "outdoor" in site["needs"]:
            conditions[site["site_id"]] = weather.resolve_condition(override, None, settings.rain_threshold)
        elif override:
            conditions[site["site_id"]] = override
    flags: dict = {}
    flags_error = False
    try:
        flags = amendments_feed.read_amendment_flags(
            sheets, settings.skipta_sheet_id, sites, date_type.fromisoformat(date), settings.lookback_days
        )
    except Exception as exc:  # the feed is an enrichment — never take the board down
        logger.warning("amendment feed unavailable: %s", exc)
        flags_error = True
    return {"crews": crews, "sites": sites, "assignments": assignments, "flags": flags,
            "conditions": conditions, "flags_error": flags_error}


class ConditionRequest(BaseModel):
    date: str
    condition: str = Field(..., max_length=40)

    @field_validator("condition")
    @classmethod
    def normalize(cls, v: str) -> str:
        return v.strip()


@app.get("/healthz")
def healthz():
    return {"status": "healthy"}


@app.get("/", response_class=HTMLResponse)
def board_page(
    request: Request,
    date: str | None = None,
    settings: Settings = Depends(get_settings),
    sheets=Depends(get_sheets),
    http_get_json=Depends(get_http_get_json),
):
    day = _valid_date(date) if date else date_type.today().isoformat()
    data = _load_day(settings, sheets, http_get_json, day)
    people_by_site: dict[str, list[dict]] = {}
    crew_by_id = {c["person_id"]: c for c in data["crews"]}
    for assignment in data["assignments"]:
        person = crew_by_id.get(assignment["person_id"], {"person_id": assignment["person_id"], "name": assignment["person_id"], "crafts": []})
        people_by_site.setdefault(assignment["site_id"], []).append(person)
    unassigned = [c for c in data["crews"] if c["person_id"] not in {a["person_id"] for a in data["assignments"]}]
    person_names = {c["person_id"]: c["name"] or c["person_id"] for c in data["crews"]}
    site_names = {s["site_id"]: s["display"] for s in data["sites"]}
    return templates.TemplateResponse(
        request, "board.html",
        {"date": day, "sites": data["sites"], "people_by_site": people_by_site, "unassigned": unassigned,
         "conditions": data["conditions"], "flags": data["flags"], "flags_error": data["flags_error"],
         "person_names": person_names, "site_names": site_names},
    )


@app.post("/api/v1/condition")
@limiter.limit(lambda: f"{get_settings().rate_limit_per_minute}/minute")
def set_condition(
    request: Request,
    body: ConditionRequest,
    settings: Settings = Depends(get_settings),
    sheets=Depends(get_sheets),
):
    day = _valid_date(body.date)
    board.set_condition(sheets, settings.board_sheet_id, day, body.condition)
    return {"date": day, "condition": body.condition}


class SuggestRequest(BaseModel):
    date: str


class ApplyMove(BaseModel):
    person_id: str
    from_site: str = ""
    to_site: str
    reason: str = ""


class ApplyRequest(BaseModel):
    date: str
    moves: list[ApplyMove]


@app.post("/api/v1/suggest")
@limiter.limit(lambda: f"{get_settings().rate_limit_per_minute}/minute")
def suggest(
    request: Request,
    body: SuggestRequest,
    settings: Settings = Depends(get_settings),
    sheets=Depends(get_sheets),
    http_get_json=Depends(get_http_get_json),
    plan_fn=Depends(get_plan),
):
    day = _valid_date(body.date)
    data = _load_day(settings, sheets, http_get_json, day)
    context = planner.build_context(day, data["crews"], data["sites"], data["assignments"], data["flags"], data["conditions"])
    try:
        plan = plan_fn(context, settings)
    except planner.PlanError as exc:
        raise HTTPException(status_code=502, detail=f"Could not draft a plan: {exc}") from exc
    verified = verifier.verify_moves([m.model_dump() for m in plan.moves], data["crews"], data["sites"], data["assignments"])
    warnings = verifier.coverage_warnings(data["crews"], data["sites"], data["assignments"], verified)
    return {"summary": plan.summary, "moves": [v.as_dict() for v in verified], "warnings": warnings}


@app.post("/api/v1/apply")
@limiter.limit(lambda: f"{get_settings().rate_limit_per_minute}/minute")
def apply(
    request: Request,
    body: ApplyRequest,
    settings: Settings = Depends(get_settings),
    sheets=Depends(get_sheets),
):
    day = _valid_date(body.date)
    crews = board.read_crews(sheets, settings.board_sheet_id)
    sites = board.read_sites(sheets, settings.board_sheet_id)
    assignments = board.read_assignments(sheets, settings.board_sheet_id, day)
    verified = verifier.verify_moves([m.model_dump() for m in body.moves], crews, sites, assignments)
    invalid = [v.as_dict() for v in verified if not v.valid]
    if invalid:
        raise HTTPException(status_code=422, detail={"message": "invalid moves — nothing applied", "moves": invalid})
    applied = board.apply_moves(sheets, settings.board_sheet_id, day, [{"person_id": v.person_id, "to_site": v.to_site} for v in verified])
    logger.info("applied %d moves on %s", applied, day)
    return {"applied": applied}
