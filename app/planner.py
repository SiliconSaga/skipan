"""One structured Gemini call proposes moves; it never writes. The verifier gates downstream."""
import json
import logging

from pydantic import BaseModel, ValidationError

logger = logging.getLogger("skipan.planner")


class PlanMove(BaseModel):
    person_id: str
    from_site: str = ""
    to_site: str
    reason: str = ""


class Plan(BaseModel):
    moves: list[PlanMove] = []
    summary: str = ""


class PlanError(Exception):
    """Every configured model failed to produce a schema-valid plan."""


PLAN_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "moves": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "person_id": {"type": "STRING"},
                    "from_site": {"type": "STRING", "description": "Current site, empty when currently unassigned"},
                    "to_site": {"type": "STRING"},
                    "reason": {"type": "STRING", "description": "One sentence"},
                },
                "required": ["person_id", "to_site"],
            },
        },
        "summary": {"type": "STRING", "description": "Two-sentence plan summary for the dispatcher"},
    },
    "required": ["moves"],
}

PROMPT = (
    "You are a field-crew dispatcher's assistant. Given today's schedule context as JSON, propose crew moves that "
    "address scope changes and site conditions. Each site's needs list says what kind of work it holds: a site whose "
    "needs include outdoor is weather-exposed, and in rain or rain-risk conditions prefer moving people off sites "
    "whose only need is outdoor onto sites with indoor work. Move ONLY people listed in the context, ONLY between "
    "sites listed in the context, prefer moves that keep each site's needed crafts covered, use an empty from_site "
    "exactly when the person is currently unassigned, and give a one-sentence reason per move. In every reason and in "
    "the summary refer to people and sites by their name and job fields, never by ids; ids belong only in the "
    "person_id, from_site, and to_site fields. Propose no move when none is needed.\n\nContext:\n{context}"
)


def build_context(date: str, crews, sites, assignments, flags, conditions) -> dict:
    assigned_to = {a["person_id"]: a["site_id"] for a in assignments}
    return {
        "date": date,
        "people": [
            {"person_id": c["person_id"], "name": c.get("name") or c["person_id"], "crafts": c["crafts"],
             "assigned_to": assigned_to.get(c["person_id"], "")}
            for c in crews
        ],
        "sites": [
            {
                "site_id": s["site_id"], "job": s.get("display") or s["site_id"],
                "needs": s["needs"], "needed_crafts": s["needed_crafts"],
                "condition": conditions.get(s["site_id"], "clear"),
                "scope_changes": flags.get(s["site_id"], []),
            }
            for s in sites
        ],
    }


def suggest_plan(context: dict, *, model_factory, model_names, max_output_tokens) -> Plan:
    from vertexai.generative_models import GenerationConfig

    config = GenerationConfig(
        response_mime_type="application/json", response_schema=PLAN_SCHEMA, max_output_tokens=max_output_tokens
    )
    prompt = PROMPT.format(context=json.dumps(context))
    for name in model_names:
        try:
            response = model_factory(name).generate_content(prompt, generation_config=config)
            return Plan.model_validate_json(response.text)
        except (ValidationError, ValueError) as exc:
            logger.warning("model %s returned schema-invalid plan: %s", name, exc)
        except Exception as exc:
            logger.warning("model %s failed: %s", name, exc)
    raise PlanError(f"all models failed to draft a plan: {model_names}")
