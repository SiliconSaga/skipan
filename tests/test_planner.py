import json

import pytest

from app.planner import Plan, PlanError, build_context, suggest_plan

PLAN_JSON = '{"moves": [{"person_id": "p1", "from_site": "s1", "to_site": "wh", "reason": "rain risk"}], "summary": "Shift Ada to the depot."}'


class FakeResponse:
    def __init__(self, text):
        self.text = text


class FakeModel:
    def __init__(self, text=None, error=None):
        self.text, self.error = text, error
        self.prompt = None

    def generate_content(self, prompt, generation_config=None):
        if self.error:
            raise self.error
        self.prompt = prompt
        return FakeResponse(self.text)


def factory_for(models):
    calls = []

    def factory(name):
        calls.append(name)
        return models[len(calls) - 1]

    factory.calls = calls
    return factory


def test_build_context_is_compact_and_complete():
    context = build_context(
        "2026-07-17",
        [{"person_id": "p1", "name": "Ada", "crafts": ["electrician"], "crew": "alpha"}],
        [{"site_id": "s1", "customer_name": "Smith", "needed_crafts": ["electrician"], "needs": ["outdoor"], "lat": 1.0, "lon": 2.0, "address": "", "notes": ""}],
        [{"row": 2, "person_id": "p1", "site_id": "s1", "note": ""}],
        {"s1": [{"proposal_name": "span.pdf", "total": 500.0}]},
        {"s1": "rain-risk"},
    )
    assert context["date"] == "2026-07-17"
    assert context["people"] == [{"person_id": "p1", "crafts": ["electrician"], "assigned_to": "s1"}]
    assert context["sites"][0]["condition"] == "rain-risk"
    assert context["sites"][0]["scope_changes"] == [{"proposal_name": "span.pdf", "total": 500.0}]


def test_suggest_plan_valid_and_prompt_carries_context():
    model = FakeModel(text=PLAN_JSON)
    plan = suggest_plan({"date": "d"}, model_factory=factory_for([model]), model_names=["m1"], max_output_tokens=512)
    assert isinstance(plan, Plan) and plan.moves[0].to_site == "wh"
    assert json.dumps({"date": "d"}) in model.prompt


def test_suggest_plan_falls_back_then_raises():
    factory = factory_for([FakeModel(text="junk"), FakeModel(error=RuntimeError("quota"))])
    with pytest.raises(PlanError):
        suggest_plan({}, model_factory=factory, model_names=["m1", "m2"], max_output_tokens=512)
    assert factory.calls == ["m1", "m2"]
