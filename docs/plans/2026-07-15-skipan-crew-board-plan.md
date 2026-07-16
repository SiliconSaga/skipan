# Skipan Crew Board Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Skipan live at `https://skipan.cmdbee.org` — a phone-first crew board that flags Skipta amendment fallout and rain risk per site, and turns one tap into a Gemini-proposed, verifier-gated, human-applied crew rearrangement.

**Architecture:** Standalone FastAPI sibling of Skipta (spec: `skipan-crew-board-design-draft.md`, adopted into the repo as `docs/plans/2026-07-15-skipan-crew-board-design.md` in Task 1). One spreadsheet is the database (Crews/Sites/Assignments/Days); Skipta's Amendments sheet is a read-only integration bus; open-meteo supplies forecasts with a Days-tab override; the suggest pipeline is one Gemini structured call gated by a pure deterministic verifier. Everything degrades soft except the board sheet.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, google-cloud-aiplatform (<1.160), google-api-python-client (Sheets v4 only — no Drive, no GCS), httpx (runtime, for open-meteo), Jinja2, pytest/ruff, kustomize + Traefik Gateway, GitHub Actions → ghcr.

## Global Constraints

- Repo: `SiliconSaga/skipan`; namespace `skipan`; hostname `skipan.cmdbee.org`; image `ghcr.io/siliconsaga/skipan`.
- Identity: `skipan-gsa@teralivekubernetes.iam.gserviceaccount.com`, KSA `skipan-sa` in ns `skipan`. Scopes: `cloud-platform` + `spreadsheets` only.
- Two sheet ids in config: `SKIPAN_BOARD_SHEET_ID` (Editor) and `SKIPAN_SKIPTA_SHEET_ID` (Viewer — Skipta's existing spreadsheet). The human creates/seeds/shares both; Task 3 verifies.
- Board tabs exactly: `Crews` (person_id,name,crafts,crew — A:D), `Sites` (site_id,customer_name,address,lat,lon,work_type,needed_crafts,notes — A:H), `Assignments` (date,person_id,site_id,note — A:D), `Days` (date,condition_override,note — A:C). Short rows pad on read (Sheets truncates trailing empties).
- Skipta Amendments columns consumed (read-only, A:P): customer_name idx2, total idx6, status idx7, signed_at idx9, kind idx10, proposal_name idx12.
- Suggest pipeline contract: the LLM never writes; verifier gates every move; `apply` re-verifies server-side against fresh reads; invalid anywhere → 422, nothing applied. Empty `from_site` is valid exactly when the person is unassigned that date.
- Condition resolution order: `Days.condition_override` > forecast (`rain-risk` iff precipitation probability ≥ `SKIPAN_RAIN_THRESHOLD`, default 50) > `clear`; open-meteo failure → `unknown` (soft).
- Weather applies to `work_type=outdoor` sites with both lat and lon present; others render no badge.
- Dependency pins: `google-cloud-aiplatform>=1.60,<1.160` (vertexai.generative_models removal cap — verified line), `httpx>=0.27,<1.0` runtime.
- GDD rules as before: `ws commit/push/cr` with bodyfiles at workspace `.commits/`; ONE shell command per call (no `&&`/`;`/`|`, also not inside quoted args); `ws test skipan`/`ws lint skipan` only (adapter → `make test`/`make lint`); sub-agent co-author files `.tmp/gdd-agent-sessions/<session>--<label>.env`; NO pushes except Task 1's scaffold push to main and the Task 14 checkpoint; k8s writes only via `ws k8s … -n skipan` after extending the guard scope.
- Test fakes live in `tests/fakes.py` (importable module — avoids the cross-test-file import weave from Skipta).
- Suite must stay pristine: pyproject filters the Starlette TestClient deprecation warning (same line as Skipta's).

## Prerequisites (human-side, morning)

Create the board spreadsheet with the four tabs + headers above, seed a demo day (2 crews / ~6 people with crafts like `electrician, apprentice, hvac`; 3 sites — two outdoor with real-ish lat/lon, one `work_type=warehouse`; Assignments rows for the demo date; Days empty), share it Editor with `skipan-gsa@…` (after Task 3 creates the GSA) and share the SKIPTA spreadsheet Viewer with the same GSA. Provide both sheet ids.

---

### Task 1: Repo bootstrap — SiliconSaga/skipan + scaffold + docs adoption

**Files:**
- Create in `components/skipan/`: `README.md`, `.gitignore`, `requirements.txt`, `requirements-dev.txt`, `pyproject.toml`, `Makefile`, `.env.template`, `catalog-info.yaml`, `docs/plans/2026-07-15-skipan-crew-board-design.md` (copied verbatim from `.superpowers/sdd/skipan-crew-board-design-draft.md`), `docs/plans/2026-07-15-skipan-crew-board-plan.md` (this plan, copied from `.superpowers/sdd/skipan-crew-board-plan-draft.md`)
- Modify: `ecosystem.local.yaml` (workspace root — temporary entry until Task 2's realm CR merges)

**Interfaces:**
- Produces: cloned `components/skipan` on `main`, ws targetability, pinned deps, docs in-repo.

- [ ] **Step 1: Create the repo** — Run: `ws gh repo create SiliconSaga/skipan --public --description "AI-suggested crew scheduling board (GDD showcase, sibling of skipta)"`
- [ ] **Step 2: Register temporarily** — add to `ecosystem.local.yaml` `components:` (Edit tool):

```yaml
  skipan:
    tier: supporting
```

- [ ] **Step 3: Clone** — Run: `ws clone skipan` (empty-repo warning fine; if no branch, `git -C components/skipan checkout -b main`).
- [ ] **Step 4: Write the scaffold files.**

`.gitignore`:

```gitignore
.venv/
__pycache__/
*.pyc
.pytest_cache/
.ruff_cache/
.env
```

`requirements.txt`:

```text
fastapi>=0.115,<1.0
uvicorn[standard]>=0.30,<1.0
# <1.160: vertexai.generative_models is past its announced removal date; 1.159 verified to still ship it
google-cloud-aiplatform>=1.60,<1.160
google-api-python-client>=2.100,<3.0
google-auth>=2.30,<3.0
httpx>=0.27,<1.0
jinja2>=3.1,<4.0
pydantic>=2.7,<3.0
python-dotenv>=1.0,<2.0
slowapi>=0.1.9,<0.2
```

`requirements-dev.txt`:

```text
-r requirements.txt
pytest>=8.0,<9.0
ruff>=0.5,<1.0
```

`pyproject.toml`:

```toml
[tool.ruff]
line-length = 110
target-version = "py311"

[tool.pytest.ini_options]
testpaths = ["tests"]
filterwarnings = [
    # Third-party deprecation inside fastapi's TestClient import; nothing actionable here.
    "ignore:Using `httpx` with `starlette.testclient` is deprecated",
]
```

`Makefile`:

```make
PY := $(wildcard .venv/Scripts/python.exe)
ifeq ($(PY),)
PY := .venv/bin/python
endif

test:
	$(PY) -m pytest

lint:
	$(PY) -m ruff check .

run:
	$(PY) -m uvicorn app.main:app --reload --port 8001
```

`.env.template`:

```env
GCP_PROJECT_ID=teralivekubernetes
GCP_REGION=us-east1
SKIPAN_BOARD_SHEET_ID=
SKIPAN_SKIPTA_SHEET_ID=
SKIPAN_BASE_URL=http://localhost:8001
SKIPAN_MODEL_NAMES=gemini-2.5-flash,gemini-2.5-flash-lite,gemini-2.0-flash-001
MAX_OUTPUT_TOKENS=1024
RATE_LIMIT_PER_MINUTE=10
SKIPAN_RAIN_THRESHOLD=50
SKIPAN_LOOKBACK_DAYS=14
```

`catalog-info.yaml` (inert until the Leidangr reflection; conventions per its Phase 3 model):

```yaml
apiVersion: backstage.io/v1alpha1
kind: Component
metadata:
  name: skipan
  description: AI-suggested crew scheduling board — proposes, a human disposes.
  annotations:
    siliconsaga.org/aspects: 'operational-readiness'
spec:
  type: service
  lifecycle: experimental
  owner: group:default/siliconsaga
```

`README.md`:

```markdown
# Skipan

**Skipan** is Old Norse for arrangement, order, disposition — the act of putting things in their places. Beside its sibling [Skipta](https://github.com/SiliconSaga/skipta) ("the exchange") the pair reads: an amendment changes the work, Skipan rearranges the people.

Skipan is a phone-first crew board — a GDD showcase. Site cards show assigned people, craft coverage, a real weather badge (open-meteo, with a manual override for demo determinism), and amendment fallout read straight from Skipta's spreadsheet (the sheet is the integration bus — no webhooks, no coupling). One tap asks Gemini for a rearrangement plan; a deterministic verifier gates every proposed move; nothing changes until the dispatcher applies it.

Docs: [design](docs/plans/2026-07-15-skipan-crew-board-design.md) · [plan](docs/plans/2026-07-15-skipan-crew-board-plan.md)

## Local dev

1. `python -m venv .venv`
2. `.venv/Scripts/python -m pip install -r requirements-dev.txt` (POSIX: `.venv/bin/python`)
3. Copy `.env.template` to `.env`, fill both sheet ids.
4. `gcloud auth application-default login --impersonate-service-account=skipan-gsa@teralivekubernetes.iam.gserviceaccount.com`
5. `make run` → http://localhost:8001

## Deploy

GitHub Actions builds `ghcr.io/siliconsaga/skipan` on push to main; apply `k8s/base` with kustomize (workspace: `ws k8s apply -k components/skipan/k8s/base -n skipan`).
```

- [ ] **Step 5: Adopt the docs** — copy the two draft files from `.superpowers/sdd/` into `docs/plans/` under their dated names (Read + Write; adjust nothing but the draft-home note if present).
- [ ] **Step 6: venv** — Run: `python -m venv components/skipan/.venv` then `components/skipan/.venv/Scripts/python -m pip install -r components/skipan/requirements-dev.txt`
- [ ] **Step 7: Commit + push main** — bodyfile `.commits/skipan-scaffold.md`:

```markdown
---
message: "chore: scaffold skipan — deps, Makefile, env template, catalog entry, design + plan docs"
add:
  - README.md
  - .gitignore
  - requirements.txt
  - requirements-dev.txt
  - pyproject.toml
  - Makefile
  - .env.template
  - catalog-info.yaml
  - docs/plans/2026-07-15-skipan-crew-board-design.md
  - docs/plans/2026-07-15-skipan-crew-board-plan.md
---

Initial scaffold for Skipan, Skipta's scheduling sibling, per the approved in-repo design. Ships the Backstage catalog-info from day one so the future Leidangr reflection is a file-away, and adopts the design + plan docs with the component per workspace convention.
```

Run: `ws commit skipan .commits/skipan-scaffold.md` then `ws push skipan main`.

### Task 2: Realm wiring — ecosystem entry + adapter (CR)

**Files:**
- Modify: `realms/realm-siliconsaga/ecosystem.yaml` (Tier 3, after the `skipta:` block)
- Create: `realms/realm-siliconsaga/adapters/skipan.yaml`

**Interfaces:**
- Produces: `ws test skipan` → `make test`, `ws lint skipan` → `make lint`; canonical declaration (namespace `skipan`, tier 3).

- [ ] **Step 1:** Refresh realm main first (the round-1 lesson): `git -C realms/realm-siliconsaga fetch siliconsaga main` then `git -C realms/realm-siliconsaga merge --ff-only siliconsaga/main` (from main; stash-protect any human WIP and restore it), then `git -C realms/realm-siliconsaga checkout -b feat/skipan-component`.
- [ ] **Step 2:** Add to `ecosystem.yaml` after the `skipta:` entry:

```yaml
  # skipan — AI-suggested crew scheduling board, skipta's sibling ("the
  # arrangement" beside "the exchange"). Design doc lives in the component
  # repo: docs/plans/2026-07-15-skipan-crew-board-design.md.
  skipan:
    tier: 3
    chartVersion: "0.0.0"
    namespace: skipan
```

- [ ] **Step 3:** `adapters/skipan.yaml`:

```yaml
# skipan adapter — build/test commands and AI context pointers
commands:
  test: "make test"
  lint: "make lint"

ai_context:
  - path: "README.md"
    description: "Service overview, local dev, deploy"
```

- [ ] **Step 4:** Verify with `ws orient` (skipan adapter row resolves).
- [ ] **Step 5:** Commit/push/CR — bodyfile `.commits/realm-skipan.md` (message `feat: declare skipan component (tier 3) + test/lint adapter`, add: `ecosystem.yaml`, `adapters/skipan.yaml`; body: one sentence referencing the component-repo design doc). Run `ws commit realm-siliconsaga .commits/realm-skipan.md`, `ws push realm-siliconsaga`, `cp templates/change.md .crs/realm-skipan.md`, fill Summary/Test plan (ws orient row, ws list), `ws cr realm-siliconsaga "feat: declare skipan component + adapter" .crs/realm-skipan.md`. After merge, drop the temp `skipan:` block from `ecosystem.local.yaml`.

### Task 3: GCP identity — skipan-gsa + WI + verify script

**Files:**
- Create: `components/skipan/scripts/verify_access.py`

One gcloud command per call:

- [ ] **Step 1:** `gcloud iam service-accounts create skipan-gsa --project teralivekubernetes --display-name "Skipan crew board"`
- [ ] **Step 2:** `gcloud projects add-iam-policy-binding teralivekubernetes --member serviceAccount:skipan-gsa@teralivekubernetes.iam.gserviceaccount.com --role roles/aiplatform.user`
- [ ] **Step 3:** `gcloud iam service-accounts add-iam-policy-binding skipan-gsa@teralivekubernetes.iam.gserviceaccount.com --role roles/iam.workloadIdentityUser --member "serviceAccount:teralivekubernetes.svc.id.goog[skipan/skipan-sa]"`
- [ ] **Step 4:** `gcloud iam service-accounts add-iam-policy-binding skipan-gsa@teralivekubernetes.iam.gserviceaccount.com --role roles/iam.serviceAccountTokenCreator --member user:cervator@gmail.com`
- [ ] **Step 5 (human):** create/seed/share the board sheet (Editor) + Skipta sheet (Viewer) with `skipan-gsa@…`; run `! gcloud auth application-default login --impersonate-service-account=skipan-gsa@teralivekubernetes.iam.gserviceaccount.com`; provide both ids.
- [ ] **Step 6:** Write `scripts/verify_access.py`:

```python
"""One-shot access check: prints tab names of both spreadsheets via impersonated ADC."""
import sys

import google.auth
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/spreadsheets",
]

creds, _ = google.auth.default(scopes=SCOPES)
sheets = build("sheets", "v4", credentials=creds, cache_discovery=False)
for sid in sys.argv[1:]:
    meta = sheets.spreadsheets().get(spreadsheetId=sid).execute()
    print(sid, [s["properties"]["title"] for s in meta["sheets"]])
```

- [ ] **Step 7:** Run it with both ids — expect `['Crews','Sites','Assignments','Days']` and Skipta's `['Panels','Breakers','Amendments']`.
- [ ] **Step 8:** Commit — bodyfile `.commits/skipan-verify.md` (message `chore: add dual-sheet access verifier`, add: `scripts/verify_access.py`).

### Task 4: `app/config.py`

**Files:**
- Create: `components/skipan/app/__init__.py` (empty), `components/skipan/app/config.py`
- Test: `components/skipan/tests/__init__.py` (empty), `components/skipan/tests/test_config.py`

**Interfaces:**
- Produces: frozen dataclass `Settings(project_id, region, board_sheet_id, skipta_sheet_id, base_url, model_names: list[str], max_output_tokens: int, rate_limit_per_minute: int, rain_threshold: int, lookback_days: int)` + `Settings.from_env()`.

- [ ] **Step 1: Failing test** — `tests/test_config.py`:

```python
from app.config import Settings


def test_from_env_reads_and_defaults(monkeypatch):
    monkeypatch.setenv("GCP_PROJECT_ID", "proj")
    monkeypatch.setenv("SKIPAN_BOARD_SHEET_ID", "board123")
    monkeypatch.setenv("SKIPAN_SKIPTA_SHEET_ID", "skipta456")
    monkeypatch.setenv("SKIPAN_MODEL_NAMES", "gemini-2.5-flash, gemini-2.0-flash-001")
    s = Settings.from_env()
    assert s.project_id == "proj"
    assert s.board_sheet_id == "board123" and s.skipta_sheet_id == "skipta456"
    assert s.model_names == ["gemini-2.5-flash", "gemini-2.0-flash-001"]
    assert s.rain_threshold == 50 and s.lookback_days == 14
    assert s.region == "us-east1" and s.base_url == "http://localhost:8001"
```

- [ ] **Step 2:** `ws test skipan` → FAIL (`ModuleNotFoundError: app.config`).
- [ ] **Step 3: Implement** — `app/config.py`:

```python
"""Environment-driven settings. A .env at the component root is honored for local dev."""
import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()

DEFAULT_MODELS = "gemini-2.5-flash,gemini-2.5-flash-lite,gemini-2.0-flash-001"


@dataclass(frozen=True)
class Settings:
    project_id: str
    region: str
    board_sheet_id: str
    skipta_sheet_id: str
    base_url: str
    model_names: list[str] = field(default_factory=list)
    max_output_tokens: int = 1024
    rate_limit_per_minute: int = 10
    rain_threshold: int = 50
    lookback_days: int = 14

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            project_id=os.getenv("GCP_PROJECT_ID", ""),
            region=os.getenv("GCP_REGION", "us-east1"),
            board_sheet_id=os.getenv("SKIPAN_BOARD_SHEET_ID", ""),
            skipta_sheet_id=os.getenv("SKIPAN_SKIPTA_SHEET_ID", ""),
            base_url=os.getenv("SKIPAN_BASE_URL", "http://localhost:8001"),
            model_names=[m.strip() for m in os.getenv("SKIPAN_MODEL_NAMES", DEFAULT_MODELS).split(",") if m.strip()],
            max_output_tokens=int(os.getenv("MAX_OUTPUT_TOKENS", "1024")),
            rate_limit_per_minute=int(os.getenv("RATE_LIMIT_PER_MINUTE", "10")),
            rain_threshold=int(os.getenv("SKIPAN_RAIN_THRESHOLD", "50")),
            lookback_days=int(os.getenv("SKIPAN_LOOKBACK_DAYS", "14")),
        )
```

- [ ] **Step 4:** `ws test skipan` → PASS; `ws lint skipan` clean.
- [ ] **Step 5: Commit** — bodyfile `.commits/skipan-config.md` (message `feat: env-driven Settings`, add: `app/__init__.py`, `app/config.py`, `tests/__init__.py`, `tests/test_config.py`).

### Task 5: Google clients + board reads + the shared fakes module

**Files:**
- Create: `components/skipan/app/google_clients.py`, `components/skipan/app/board.py`, `components/skipan/tests/fakes.py`
- Test: `components/skipan/tests/test_board_reads.py`

**Interfaces:**
- Produces: `google_clients.get_credentials()`, `build_sheets(creds)`, `make_model_factory(project_id, region)`, `read_values(sheets, sid, a1_range)`. `board.read_crews(sheets, sid) -> list[dict{person_id,name,crafts:list,crew}]`, `read_sites(sheets, sid) -> list[dict{site_id,customer_name,address,lat:float|None,lon:float|None,work_type,needed_crafts:list,notes}]`, `read_assignments(sheets, sid, date) -> list[dict{row:int,person_id,site_id,note}]` (row = 1-based sheet row), `read_condition_override(sheets, sid, date) -> str`, plus `board._csv(s) -> list[str]`. `tests/fakes.py` exports `FakeSheets(stores: dict[sid, dict[tab, list[rows]]])` supporting `values().get/append/update` routed by spreadsheetId + tab, single-cell updates like `Assignments!C3`, and range updates like `Days!B2`.

- [ ] **Step 1: Write the fakes module** — `tests/fakes.py`:

```python
"""Shared Sheets fake: multiple spreadsheets keyed by id, tabs keyed by name. Mirrors just enough of the values() surface."""
import re


class FakeValues:
    def __init__(self, stores):
        self.stores = stores  # sid -> {tab: [rows]} (no header rows)

    def _tab(self, range):
        return range.split("!")[0]

    def get(self, spreadsheetId, range):
        self._result = {"values": self.stores.get(spreadsheetId, {}).get(self._tab(range), [])}
        return self

    def append(self, spreadsheetId, range, valueInputOption, body):
        self.stores.setdefault(spreadsheetId, {}).setdefault(self._tab(range), []).extend(body["values"])
        self._result = {}
        return self

    def update(self, spreadsheetId, range, valueInputOption, body):
        tab = self._tab(range)
        cell = range.split("!")[1]
        m = re.match(r"([A-Z]+)(\d+)", cell)
        col = ord(m.group(1)) - ord("A")  # single-letter columns only — fine for A..H
        row = int(m.group(2)) - 2  # store index (row 1 = header)
        rows = self.stores[spreadsheetId][tab]
        while len(rows[row]) <= col:
            rows[row].append("")
        for offset, value in enumerate(body["values"][0]):
            rows[row][col + offset] = value
        self._result = {}
        return self

    def execute(self):
        return self._result


class FakeSheets:
    def __init__(self, stores):
        self._values = FakeValues(stores)
        self.stores = self._values.stores

    def spreadsheets(self):
        return self

    def values(self):
        return self._values
```

- [ ] **Step 2: Failing tests** — `tests/test_board_reads.py`:

```python
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
    assert sites[2]["work_type"] == "warehouse"


def test_read_assignments_filters_by_date_with_rows():
    got = read_assignments(make_sheets(), BOARD, "2026-07-16")
    assert [(a["row"], a["person_id"], a["site_id"]) for a in got] == [(2, "p1", "s1"), (3, "p2", "s2")]


def test_condition_override_hit_and_miss():
    sheets = make_sheets()
    assert read_condition_override(sheets, BOARD, "2026-07-17") == "rain"
    assert read_condition_override(sheets, BOARD, "2026-07-16") == ""
```

- [ ] **Step 3:** `ws test skipan` → FAIL (`ModuleNotFoundError: app.board`).
- [ ] **Step 4: Implement** — `app/google_clients.py`:

```python
"""All Google client construction lives here; everything downstream takes injected clients."""
import google.auth
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/spreadsheets",
]


def get_credentials():
    creds, _ = google.auth.default(scopes=SCOPES)
    return creds


def build_sheets(creds):
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def make_model_factory(project_id: str, region: str):
    def factory(model_name: str):
        import vertexai
        from vertexai.generative_models import GenerativeModel

        vertexai.init(project=project_id, location=region)
        return GenerativeModel(model_name)

    return factory


def read_values(sheets, spreadsheet_id: str, a1_range: str):
    result = sheets.spreadsheets().values().get(spreadsheetId=spreadsheet_id, range=a1_range).execute()
    return result.get("values", [])
```

and `app/board.py` (reads half):

```python
"""The board spreadsheet: Crews/Sites/Assignments/Days reads and Assignment/Days writes."""
from app.google_clients import read_values

CREWS_RANGE = "Crews!A2:D"
SITES_RANGE = "Sites!A2:H"
ASSIGN_TAB = "Assignments"
ASSIGN_RANGE = f"{ASSIGN_TAB}!A2:D"
DAYS_TAB = "Days"
DAYS_RANGE = f"{DAYS_TAB}!A2:C"


def _csv(value: str) -> list[str]:
    return [t.strip() for t in (value or "").split(",") if t.strip()]


def _pad(row: list, width: int) -> list:
    return list(row) + [""] * (width - len(row))


def _coord(value: str):
    return float(value) if value else None


def read_crews(sheets, sid: str) -> list[dict]:
    out = []
    for row in read_values(sheets, sid, CREWS_RANGE):
        p = _pad(row, 4)
        out.append({"person_id": p[0], "name": p[1], "crafts": _csv(p[2]), "crew": p[3]})
    return out


def read_sites(sheets, sid: str) -> list[dict]:
    out = []
    for row in read_values(sheets, sid, SITES_RANGE):
        p = _pad(row, 8)
        out.append({
            "site_id": p[0], "customer_name": p[1], "address": p[2],
            "lat": _coord(p[3]), "lon": _coord(p[4]), "work_type": p[5] or "outdoor",
            "needed_crafts": _csv(p[6]), "notes": p[7],
        })
    return out


def read_assignments(sheets, sid: str, date: str) -> list[dict]:
    out = []
    for index, row in enumerate(read_values(sheets, sid, ASSIGN_RANGE)):
        p = _pad(row, 4)
        if p[0] == date:
            out.append({"row": index + 2, "person_id": p[1], "site_id": p[2], "note": p[3]})
    return out


def read_condition_override(sheets, sid: str, date: str) -> str:
    for row in read_values(sheets, sid, DAYS_RANGE):
        p = _pad(row, 3)
        if p[0] == date:
            return p[1]
    return ""
```

- [ ] **Step 5:** `ws test skipan` → PASS; lint clean.
- [ ] **Step 6: Commit** — bodyfile `.commits/skipan-board-reads.md` (message `feat: google clients + board reads + shared sheet fake`, add: `app/google_clients.py`, `app/board.py`, `tests/fakes.py`, `tests/test_board_reads.py`).

### Task 6: Board writes — `apply_moves` + `set_condition`

**Files:**
- Modify: `components/skipan/app/board.py` (append)
- Test: `components/skipan/tests/test_board_writes.py`

**Interfaces:**
- Produces: `apply_moves(sheets, sid, date, moves: list[dict{person_id, to_site}]) -> int` (count applied; update-in-place when the person has a row that date, else append `[date, person_id, to_site, ""]`), `set_condition(sheets, sid, date, condition: str)` (update Days row in place or append `[date, condition, ""]`).

- [ ] **Step 1: Failing tests** — `tests/test_board_writes.py`:

```python
from app.board import apply_moves, read_assignments, read_condition_override, set_condition
from tests.fakes import FakeSheets

BOARD = "board123"


def make_sheets():
    return FakeSheets({
        BOARD: {
            "Assignments": [
                ["2026-07-16", "p1", "s1", ""],
                ["2026-07-16", "p2", "s2", "keep note"],
            ],
            "Days": [["2026-07-16", "", ""]],
        }
    })


def test_apply_moves_updates_existing_row_preserving_note():
    sheets = make_sheets()
    applied = apply_moves(sheets, BOARD, "2026-07-16", [{"person_id": "p2", "to_site": "wh"}])
    assert applied == 1
    got = {a["person_id"]: a for a in read_assignments(sheets, BOARD, "2026-07-16")}
    assert got["p2"]["site_id"] == "wh" and got["p2"]["note"] == "keep note"


def test_apply_moves_appends_for_unassigned_person():
    sheets = make_sheets()
    apply_moves(sheets, BOARD, "2026-07-16", [{"person_id": "p9", "to_site": "s1"}])
    got = {a["person_id"]: a["site_id"] for a in read_assignments(sheets, BOARD, "2026-07-16")}
    assert got["p9"] == "s1"


def test_set_condition_updates_then_appends():
    sheets = make_sheets()
    set_condition(sheets, BOARD, "2026-07-16", "rain")
    assert read_condition_override(sheets, BOARD, "2026-07-16") == "rain"
    set_condition(sheets, BOARD, "2026-07-18", "clear")
    assert read_condition_override(sheets, BOARD, "2026-07-18") == "clear"
```

- [ ] **Step 2:** `ws test skipan` → FAIL (ImportError).
- [ ] **Step 3: Implement** — append to `app/board.py`:

```python
def apply_moves(sheets, sid: str, date: str, moves: list[dict]) -> int:
    current = {a["person_id"]: a for a in read_assignments(sheets, sid, date)}
    applied = 0
    for move in moves:
        person, to_site = move["person_id"], move["to_site"]
        existing = current.get(person)
        if existing:
            sheets.spreadsheets().values().update(
                spreadsheetId=sid, range=f"{ASSIGN_TAB}!C{existing['row']}", valueInputOption="RAW",
                body={"values": [[to_site]]},
            ).execute()
        else:
            sheets.spreadsheets().values().append(
                spreadsheetId=sid, range=ASSIGN_RANGE, valueInputOption="RAW",
                body={"values": [[date, person, to_site, ""]]},
            ).execute()
        applied += 1
    return applied


def set_condition(sheets, sid: str, date: str, condition: str) -> None:
    for index, row in enumerate(read_values(sheets, sid, DAYS_RANGE)):
        if _pad(row, 3)[0] == date:
            sheets.spreadsheets().values().update(
                spreadsheetId=sid, range=f"{DAYS_TAB}!B{index + 2}", valueInputOption="RAW",
                body={"values": [[condition]]},
            ).execute()
            return
    sheets.spreadsheets().values().append(
        spreadsheetId=sid, range=DAYS_RANGE, valueInputOption="RAW", body={"values": [[date, condition, ""]]}
    ).execute()
```

- [ ] **Step 4:** `ws test skipan` → PASS; lint clean.
- [ ] **Step 5: Commit** — bodyfile `.commits/skipan-board-writes.md` (message `feat: assignment moves + condition override writes`, add: `app/board.py`, `tests/test_board_writes.py`).

### Task 7: Weather — open-meteo + condition resolution

**Files:**
- Create: `components/skipan/app/weather.py`
- Test: `components/skipan/tests/test_weather.py`

**Interfaces:**
- Produces: `fetch_precip_probability(http_get_json, lat: float, lon: float, date: str) -> int | None` (None on ANY failure — soft), `resolve_condition(override: str, precip: int | None, threshold: int) -> str` (override wins; None → "unknown"; ≥ threshold → "rain-risk"; else "clear"), `default_http_get_json(url) -> dict` (httpx, 5s timeout), `OPEN_METEO_URL` template.

- [ ] **Step 1: Failing tests** — `tests/test_weather.py`:

```python
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
```

- [ ] **Step 2:** `ws test skipan` → FAIL.
- [ ] **Step 3: Implement** — `app/weather.py`:

```python
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
```

- [ ] **Step 4:** `ws test skipan` → PASS; lint clean.
- [ ] **Step 5: Commit** — bodyfile `.commits/skipan-weather.md` (message `feat: open-meteo forecast with soft failure + override-first resolution`, add: `app/weather.py`, `tests/test_weather.py`).

### Task 8: Amendments feed — Skipta's sheet as the bus

**Files:**
- Create: `components/skipan/app/amendments_feed.py`
- Test: `components/skipan/tests/test_amendments_feed.py`

**Interfaces:**
- Consumes: `read_values` (Task 5), Skipta column indices from Global Constraints.
- Produces: `read_amendment_flags(sheets, skipta_sid, sites, today: datetime.date, lookback_days) -> dict[site_id, list[dict{proposal_name, total: float}]]` — signed + kind=amend + within lookback, matched to sites by case-insensitive customer_name. Raises nothing itself beyond what Sheets raises (the route treats any exception as soft).

- [ ] **Step 1: Failing tests** — `tests/test_amendments_feed.py`:

```python
from datetime import date

from app.amendments_feed import read_amendment_flags
from tests.fakes import FakeSheets

SKIPTA = "skipta456"
SITES = [
    {"site_id": "s1", "customer_name": "Smith"},
    {"site_id": "s2", "customer_name": "Rasmus"},
]


def row(customer, total, status, signed_at, kind, proposal):
    return ["aid", "c", customer, "v", "{}", "[]", total, status, "url", signed_at, kind, "fid", proposal, "", "", ""]


def make_sheets(rows):
    return FakeSheets({SKIPTA: {"Amendments": rows}})


def test_flags_signed_amend_rows_matched_to_sites():
    sheets = make_sheets([
        row("rasmus", "500.00", "signed", "2026-07-14T10:00:00+00:00", "amend", "span-quote.pdf"),
        row("Smith", "99.00", "draft", "", "amend", "x.pdf"),          # not signed
        row("Smith", "50.00", "signed", "2026-07-14T10:00:00+00:00", "new", ""),  # not an amendment
        row("Nobody", "1.00", "signed", "2026-07-14T10:00:00+00:00", "amend", "y.pdf"),  # no site
    ])
    flags = read_amendment_flags(sheets, SKIPTA, SITES, date(2026, 7, 15), 14)
    assert flags == {"s2": [{"proposal_name": "span-quote.pdf", "total": 500.00}]}


def test_lookback_window_excludes_old_rows():
    sheets = make_sheets([row("Smith", "10.00", "signed", "2026-06-01T00:00:00+00:00", "amend", "old.pdf")])
    assert read_amendment_flags(sheets, SKIPTA, SITES, date(2026, 7, 15), 14) == {}


def test_short_and_dateless_rows_are_skipped():
    sheets = make_sheets([["aid", "c", "Smith", "v", "{}", "[]", "5.00", "signed"], row("Smith", "5.00", "signed", "", "amend", "z.pdf")])
    assert read_amendment_flags(sheets, SKIPTA, SITES, date(2026, 7, 15), 14) == {}
```

- [ ] **Step 2:** `ws test skipan` → FAIL.
- [ ] **Step 3: Implement** — `app/amendments_feed.py`:

```python
"""Skipta's Amendments sheet is the integration bus: read-only, matched to sites by customer name."""
from datetime import date as date_type

from app.google_clients import read_values

AMENDMENTS_RANGE = "Amendments!A2:P"


def read_amendment_flags(sheets, skipta_sid: str, sites: list[dict], today: date_type, lookback_days: int) -> dict:
    site_by_customer = {s["customer_name"].lower(): s["site_id"] for s in sites}
    flags: dict[str, list[dict]] = {}
    for row in read_values(sheets, skipta_sid, AMENDMENTS_RANGE):
        padded = list(row) + [""] * (16 - len(row))
        if padded[7] != "signed" or (padded[10] or "new") != "amend":
            continue
        signed_prefix = padded[9][:10]
        if not signed_prefix:
            continue
        try:
            signed_on = date_type.fromisoformat(signed_prefix)
        except ValueError:
            continue
        if (today - signed_on).days > lookback_days:
            continue
        site_id = site_by_customer.get(padded[2].lower())
        if site_id:
            flags.setdefault(site_id, []).append({"proposal_name": padded[12], "total": float(padded[6] or 0)})
    return flags
```

- [ ] **Step 4:** `ws test skipan` → PASS; lint clean.
- [ ] **Step 5: Commit** — bodyfile `.commits/skipan-feed.md` (message `feat: amendment flags from the Skipta sheet bus`, add: `app/amendments_feed.py`, `tests/test_amendments_feed.py`).

### Task 9: Verifier — the UNMATCHED sibling

**Files:**
- Create: `components/skipan/app/verifier.py`
- Test: `components/skipan/tests/test_verifier.py`

**Interfaces:**
- Consumes: crews/sites/assignments dict shapes from Task 5.
- Produces: dataclass `VerifiedMove(person_id, from_site, to_site, reason, valid: bool, issues: list[str])` with `as_dict()`; `verify_moves(moves: list[dict], crews, sites, assignments) -> list[VerifiedMove]` (unknown person/site, from-site mismatch — empty from_site valid iff unassigned that date, duplicate person in the move-set); `coverage_warnings(crews, sites, assignments, verified) -> list[str]` (post-move needed-vs-present craft gaps; warnings, never blocking).

- [ ] **Step 1: Failing tests** — `tests/test_verifier.py`:

```python
from app.verifier import coverage_warnings, verify_moves

CREWS = [
    {"person_id": "p1", "name": "Ada", "crafts": ["electrician"], "crew": "alpha"},
    {"person_id": "p2", "name": "Bo", "crafts": ["hvac"], "crew": "alpha"},
]
SITES = [
    {"site_id": "s1", "customer_name": "Smith", "needed_crafts": ["electrician"], "work_type": "outdoor"},
    {"site_id": "wh", "customer_name": "—", "needed_crafts": [], "work_type": "warehouse"},
]
ASSIGNED = [{"row": 2, "person_id": "p1", "site_id": "s1", "note": ""}]


def test_valid_move_and_unassigned_person():
    verified = verify_moves(
        [{"person_id": "p1", "from_site": "s1", "to_site": "wh", "reason": "rain"},
         {"person_id": "p2", "from_site": "", "to_site": "s1", "reason": "cover"}],
        CREWS, SITES, ASSIGNED,
    )
    assert all(v.valid for v in verified)


def test_unknown_person_site_and_from_mismatch():
    verified = verify_moves(
        [{"person_id": "ghost", "from_site": "", "to_site": "s1"},
         {"person_id": "p1", "from_site": "s1", "to_site": "mars"},
         {"person_id": "p2", "from_site": "s1", "to_site": "wh"}],  # p2 is actually unassigned
        CREWS, SITES, ASSIGNED,
    )
    assert [v.valid for v in verified] == [False, False, False]
    assert any("unknown person" in i for i in verified[0].issues)
    assert any("unknown site" in i for i in verified[1].issues)
    assert any("does not match" in i for i in verified[2].issues)


def test_duplicate_person_in_move_set_invalid():
    verified = verify_moves(
        [{"person_id": "p1", "from_site": "s1", "to_site": "wh"},
         {"person_id": "p1", "from_site": "s1", "to_site": "s1"}],
        CREWS, SITES, ASSIGNED,
    )
    assert verified[1].valid is False and any("duplicate" in i for i in verified[1].issues)


def test_coverage_warns_when_needed_craft_leaves():
    verified = verify_moves([{"person_id": "p1", "from_site": "s1", "to_site": "wh", "reason": "rain"}], CREWS, SITES, ASSIGNED)
    warnings = coverage_warnings(CREWS, SITES, ASSIGNED, verified)
    assert warnings == ["s1: missing craft(s) electrician"]
```

- [ ] **Step 2:** `ws test skipan` → FAIL.
- [ ] **Step 3: Implement** — `app/verifier.py`:

```python
"""Deterministic gate for LLM-proposed moves — the UNMATCHED sibling. Pure functions, no I/O."""
from dataclasses import asdict, dataclass, field


@dataclass
class VerifiedMove:
    person_id: str
    from_site: str
    to_site: str
    reason: str
    valid: bool = True
    issues: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


def verify_moves(moves: list[dict], crews: list[dict], sites: list[dict], assignments: list[dict]) -> list[VerifiedMove]:
    people = {c["person_id"] for c in crews}
    site_ids = {s["site_id"] for s in sites}
    current = {a["person_id"]: a["site_id"] for a in assignments}
    seen: set[str] = set()
    out = []
    for move in moves:
        person = move.get("person_id", "")
        from_site = move.get("from_site", "") or ""
        to_site = move.get("to_site", "")
        issues = []
        if person not in people:
            issues.append(f"unknown person {person or '(blank)'}")
        if to_site not in site_ids:
            issues.append(f"unknown site {to_site or '(blank)'}")
        if person in people:
            actual = current.get(person, "")
            if from_site != actual:
                issues.append(f"from_site {from_site or '(unassigned)'} does not match current {actual or '(unassigned)'}")
        if person in seen:
            issues.append("duplicate move for person in this plan")
        seen.add(person)
        out.append(VerifiedMove(person, from_site, to_site, move.get("reason", ""), not issues, issues))
    return out


def coverage_warnings(crews: list[dict], sites: list[dict], assignments: list[dict], verified: list[VerifiedMove]) -> list[str]:
    post = {a["person_id"]: a["site_id"] for a in assignments}
    for move in verified:
        if move.valid:
            post[move.person_id] = move.to_site
    crafts_by_person = {c["person_id"]: set(c["crafts"]) for c in crews}
    warnings = []
    for site in sites:
        needed = set(site["needed_crafts"])
        if not needed:
            continue
        present: set[str] = set()
        for person, site_id in post.items():
            if site_id == site["site_id"]:
                present |= crafts_by_person.get(person, set())
        missing = needed - present
        if missing:
            warnings.append(f"{site['site_id']}: missing craft(s) {', '.join(sorted(missing))}")
    return warnings
```

- [ ] **Step 4:** `ws test skipan` → PASS; lint clean.
- [ ] **Step 5: Commit** — bodyfile `.commits/skipan-verifier.md` (message `feat: deterministic move verifier + craft coverage warnings`, add: `app/verifier.py`, `tests/test_verifier.py`).

### Task 10: Planner — context builder + Gemini structured call

**Files:**
- Create: `components/skipan/app/planner.py`
- Test: `components/skipan/tests/test_planner.py`

**Interfaces:**
- Consumes: model-factory contract (Skipta's: `factory(name)` → `.generate_content(prompt, generation_config=…)` → `.text`).
- Produces: pydantic `PlanMove(person_id: str, from_site: str = "", to_site: str, reason: str = "")`, `Plan(moves: list[PlanMove] = [], summary: str = "")`, `PlanError`, `PLAN_SCHEMA`, `build_context(date, crews, sites, assignments, flags, conditions: dict[site_id, str]) -> dict`, `suggest_plan(context: dict, *, model_factory, model_names, max_output_tokens) -> Plan`.

- [ ] **Step 1: Failing tests** — `tests/test_planner.py`:

```python
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
        [{"site_id": "s1", "customer_name": "Smith", "needed_crafts": ["electrician"], "work_type": "outdoor", "lat": 1.0, "lon": 2.0, "address": "", "notes": ""}],
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
```

- [ ] **Step 2:** `ws test skipan` → FAIL.
- [ ] **Step 3: Implement** — `app/planner.py`:

```python
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
    "address scope changes and site conditions. Move ONLY people listed in the context, ONLY between sites listed in "
    "the context, prefer moves that keep each site's needed crafts covered, use an empty from_site exactly when the "
    "person is currently unassigned, and give a one-sentence reason per move. Propose no move when none is needed.\n\n"
    "Context:\n{context}"
)


def build_context(date: str, crews, sites, assignments, flags, conditions) -> dict:
    assigned_to = {a["person_id"]: a["site_id"] for a in assignments}
    return {
        "date": date,
        "people": [
            {"person_id": c["person_id"], "crafts": c["crafts"], "assigned_to": assigned_to.get(c["person_id"], "")}
            for c in crews
        ],
        "sites": [
            {
                "site_id": s["site_id"], "work_type": s["work_type"], "needed_crafts": s["needed_crafts"],
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
```

- [ ] **Step 4:** `ws test skipan` → PASS; lint clean.
- [ ] **Step 5: Commit** — bodyfile `.commits/skipan-planner.md` (message `feat: plan context builder + Gemini structured planner`, add: `app/planner.py`, `tests/test_planner.py`).

### Task 11: Routes — board, condition, healthz

**Files:**
- Create: `components/skipan/app/main.py`, `components/skipan/tests/conftest.py`
- Test: `components/skipan/tests/test_routes_board.py`

**Interfaces:**
- Produces: FastAPI `app`; providers `get_settings`, `get_sheets`, `get_http_get_json`, `get_plan` (overridable); `GET /` (`?date=`), `POST /api/v1/condition {date, condition}`, `GET /healthz`. Task 12 appends `POST /api/v1/suggest` + `POST /api/v1/apply` to the same file. Board context assembly is shared via an internal `_load_day(settings, sheets, http_get_json, date) -> dict` returning `{crews, sites, assignments, flags, conditions, flags_error: bool}`.

- [ ] **Step 1: conftest** — `tests/conftest.py`:

```python
from datetime import date

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
```

(`date` import is used by Task 12's tests appended to this suite family; keep it.)

- [ ] **Step 2: Failing tests** — `tests/test_routes_board.py`:

```python
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


def test_board_survives_broken_skipta_sheet(client, fakes):
    del fakes["sheets"].stores["skipta456"]
    page = client.get("/?date=2026-07-17")
    assert page.status_code == 200
    assert "amendment feed unavailable" in page.text.lower()
```

- [ ] **Step 3:** `ws test skipan` → FAIL (conftest ImportError on app.main).
- [ ] **Step 4: Implement** — `app/main.py`:

```python
"""Skipan — crew board. Routes only; logic lives in the sibling modules."""
import logging
import os
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
_clients: dict = {}


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings.from_env()
    return _settings


def get_sheets():
    if "sheets" not in _clients:
        _clients["sheets"] = build_sheets(get_credentials())
    return _clients["sheets"]


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
    assignments = board.read_assignments(sheets, settings.board_sheet_id, date)
    override = board.read_condition_override(sheets, settings.board_sheet_id, date)
    conditions = {}
    for site in sites:
        if site["work_type"] == "outdoor" and site["lat"] is not None and site["lon"] is not None:
            precip = weather.fetch_precip_probability(http_get_json, site["lat"], site["lon"], date)
            conditions[site["site_id"]] = weather.resolve_condition(override, precip, settings.rain_threshold)
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
    return templates.TemplateResponse(
        request, "board.html",
        {"date": day, "sites": data["sites"], "people_by_site": people_by_site, "unassigned": unassigned,
         "conditions": data["conditions"], "flags": data["flags"], "flags_error": data["flags_error"]},
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
```

- [ ] **Step 5:** Also create minimal `app/templates/board.html` + `app/static/skipan.css` in THIS task so the route renders (Task 13 finishes the UI; this version must satisfy the tests):

`app/templates/board.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Skipan — crew board {{ date }}</title>
<link rel="stylesheet" href="/static/skipan.css">
</head>
<body><main>
  <h1>Skipan — {{ date }}</h1>
  {% if flags_error %}<p class="warn">Amendment feed unavailable — flags omitted.</p>{% endif %}
  {% for site in sites %}
  <section class="site">
    <h2>{{ site.site_id }} — {{ site.customer_name }} <small>{{ site.address }}</small></h2>
    {% if conditions.get(site.site_id) %}<span class="badge {{ conditions[site.site_id] }}">{{ conditions[site.site_id] }}</span>{% endif %}
    {% for flag in flags.get(site.site_id, []) %}
    <p class="flag">scope +{{ "%.2f"|format(flag.total) }} — {{ flag.proposal_name }}</p>
    {% endfor %}
    <ul>
      {% for person in people_by_site.get(site.site_id, []) %}
      <li>{{ person.name }} <small>{{ person.crafts|join(", ") }}</small></li>
      {% endfor %}
    </ul>
  </section>
  {% endfor %}
  {% if unassigned %}<section class="site"><h2>Unassigned</h2><ul>{% for person in unassigned %}<li>{{ person.name }}</li>{% endfor %}</ul></section>{% endif %}
</main></body>
</html>
```

`app/static/skipan.css`:

```css
* { box-sizing: border-box; }
body { font-family: system-ui, sans-serif; margin: 0; padding: 1rem; background: #f5f5f4; color: #1c1917; }
main { max-width: 680px; margin: 0 auto; }
h1 { font-size: 1.3rem; }
section.site { background: #fff; border: 1px solid #d6d3d1; border-radius: 8px; padding: .8rem; margin: .8rem 0; }
section.site h2 { font-size: 1.05rem; margin: 0 0 .3rem; }
.badge { display: inline-block; padding: .1rem .5rem; border-radius: 999px; font-size: .8rem; background: #e7e5e4; }
.badge.rain-risk, .badge.rain { background: #dbeafe; color: #1d4ed8; }
.badge.unknown { background: #fef3c7; }
.flag { background: #fef3c7; border: 1px solid #f59e0b; padding: .4rem .6rem; border-radius: 6px; font-size: .9rem; }
.warn { background: #fef3c7; border: 1px solid #f59e0b; padding: .8rem; border-radius: 6px; }
button { padding: .7rem 1rem; border: 0; border-radius: 6px; background: #1d4ed8; color: #fff; font-size: 1rem; }
button:disabled { background: #a8a29e; }
li small { color: #78716c; }
.move { border: 1px solid #d6d3d1; border-radius: 6px; padding: .5rem; margin: .4rem 0; }
.move.invalid { opacity: .55; text-decoration: line-through; }
.issues { color: #b91c1c; font-size: .85rem; }
```

- [ ] **Step 6:** `ws test skipan` → PASS; lint clean.
- [ ] **Step 7: Commit** — bodyfile `.commits/skipan-routes-board.md` (message `feat: board page, condition endpoint, day loader`, add: `app/main.py`, `app/templates/board.html`, `app/static/skipan.css`, `tests/conftest.py`, `tests/test_routes_board.py`).

### Task 12: Routes — suggest + apply

**Files:**
- Modify: `components/skipan/app/main.py` (append)
- Test: `components/skipan/tests/test_routes_plan.py`

**Interfaces:**
- Consumes: `_load_day`, `planner.build_context`, `verifier.verify_moves`/`coverage_warnings`, `board.apply_moves`, `get_plan` provider.
- Produces: `POST /api/v1/suggest {date}` → `{summary, moves: [VerifiedMove dicts], warnings: [str]}` (no write); `POST /api/v1/apply {date, moves: [{person_id, from_site, to_site, reason?}]}` → re-verify server-side; any invalid → 422 `{detail, moves}` and nothing applied; all valid → apply, return `{applied: n}`. `PlanError` → 502.

- [ ] **Step 1: Failing tests** — `tests/test_routes_plan.py`:

```python
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
```

- [ ] **Step 2:** `ws test skipan` → FAIL (405).
- [ ] **Step 3: Implement** — append to `app/main.py`:

```python
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
```

- [ ] **Step 4:** `ws test skipan` → PASS; lint clean.
- [ ] **Step 5: Commit** — bodyfile `.commits/skipan-routes-plan.md` (message `feat: suggest + apply — LLM proposes, verifier gates, human applies`, add: `app/main.py`, `tests/test_routes_plan.py`).

### Task 13: Board UI — suggest/apply interactions

**Files:**
- Modify: `components/skipan/app/templates/board.html` (append controls + script)
- Test: `components/skipan/tests/test_routes_board.py` (append)

**Interfaces:**
- Consumes: the JSON shapes from Task 12 exactly.
- Produces: buttons and rendering only — no new endpoints.

- [ ] **Step 1: Append failing test** to `tests/test_routes_board.py`:

```python
def test_board_ships_suggest_controls(client):
    page = client.get("/?date=2026-07-17").text
    assert 'id="suggest"' in page and 'id="apply"' in page
    assert "/api/v1/suggest" in page and "/api/v1/apply" in page
```

- [ ] **Step 2:** `ws test skipan` → FAIL.
- [ ] **Step 3: Implement** — in `board.html`, before `</main>`, insert:

```html
  <section class="site">
    <h2>Rearrange</h2>
    <label>Day condition:
      <select id="condition">
        <option value="">auto (forecast)</option>
        <option value="clear">clear</option>
        <option value="rain">rain</option>
      </select>
    </label>
    <button id="suggest">Suggest a plan</button>
    <div id="plan"></div>
    <button id="apply" hidden>Apply valid moves</button>
  </section>
<script>
const boardDate = "{{ date }}";
let currentMoves = [];
document.getElementById("condition").addEventListener("change", async (event) => {
  await fetch("/api/v1/condition", { method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({ date: boardDate, condition: event.target.value }) });
  location.reload();
});
document.getElementById("suggest").addEventListener("click", async () => {
  const planDiv = document.getElementById("plan");
  planDiv.textContent = "Thinking…";
  let resp;
  try {
    resp = await fetch("/api/v1/suggest", { method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ date: boardDate }) });
  } catch (err) { planDiv.textContent = "Failed: network error"; return; }
  if (!resp.ok) { planDiv.textContent = "Failed: " + (await resp.text()); return; }
  const data = await resp.json();
  planDiv.innerHTML = "";
  const summary = document.createElement("p");
  summary.textContent = data.summary;
  planDiv.appendChild(summary);
  currentMoves = data.moves.filter(m => m.valid);
  for (const move of data.moves) {
    const div = document.createElement("div");
    div.className = "move" + (move.valid ? "" : " invalid");
    div.textContent = `${move.person_id}: ${move.from_site || "(unassigned)"} → ${move.to_site} — ${move.reason}`;
    if (!move.valid) {
      const issues = document.createElement("div");
      issues.className = "issues";
      issues.textContent = move.issues.join("; ");
      div.appendChild(issues);
    }
    planDiv.appendChild(div);
  }
  for (const warning of data.warnings) {
    const div = document.createElement("div");
    div.className = "issues";
    div.textContent = "warning: " + warning;
    planDiv.appendChild(div);
  }
  document.getElementById("apply").hidden = currentMoves.length === 0;
});
document.getElementById("apply").addEventListener("click", async () => {
  const resp = await fetch("/api/v1/apply", { method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({ date: boardDate, moves: currentMoves }) });
  if (!resp.ok) { document.getElementById("plan").textContent = "Apply failed: " + (await resp.text()); return; }
  location.reload();
});
</script>
```

- [ ] **Step 4:** `ws test skipan` → PASS; lint clean.
- [ ] **Step 5: Commit** — bodyfile `.commits/skipan-ui.md` (message `feat: suggest/apply controls on the board`, add: `app/templates/board.html`, `tests/test_routes_board.py`).

### Task 14: Dockerfile + Actions + checkpoint push + CR

**Files:**
- Create: `components/skipan/Dockerfile`, `components/skipan/.dockerignore`, `components/skipan/.github/workflows/ci.yml`, `components/skipan/.github/workflows/image.yml`

- [ ] **Step 1:** `Dockerfile` (no WeasyPrint here — slimmer than Skipta's):

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

`.dockerignore`:

```text
.venv
.git
tests
.pytest_cache
.ruff_cache
__pycache__
```

- [ ] **Step 2:** `.github/workflows/ci.yml`:

```yaml
name: ci
on:
  push:
    branches: [main]
  pull_request:
jobs:
  test:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-python@v5
      with: {python-version: '3.11'}
    - run: pip install -r requirements-dev.txt
    - run: ruff check .
    - run: python -m pytest -v
```

- [ ] **Step 3:** `.github/workflows/image.yml` (ting/skipta pattern, image name swapped to `ghcr.io/siliconsaga/skipan`):

```yaml
name: image
on:
  push:
    branches: [main]
permissions:
  contents: read
  packages: write
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v4
    - uses: docker/setup-buildx-action@v3
    - uses: docker/login-action@v3
      with:
        registry: ghcr.io
        username: ${{ github.actor }}
        password: ${{ secrets.GITHUB_TOKEN }}
    - uses: docker/metadata-action@v5
      id: meta
      with:
        images: ghcr.io/siliconsaga/skipan
        tags: |
          type=sha,format=long
          type=raw,value=latest,enable={{is_default_branch}}
    - uses: docker/build-push-action@v6
      with:
        context: .
        push: true
        tags: ${{ steps.meta.outputs.tags }}
        labels: ${{ steps.meta.outputs.labels }}
        cache-from: type=gha
        cache-to: type=gha,mode=max
```

- [ ] **Step 4:** `ws test skipan` + `ws lint skipan` green; commit — bodyfile `.commits/skipan-ci.md` (message `feat: Dockerfile + Actions ci/image workflows (ghcr)`, add: the four files). STOP — no push yet.
- [ ] **Step 5 (controller):** checkpoint push (`ws push skipan` — the branch strategy mirrors Skipta: Tasks 4–14 on `feat/crew-board-mvp`, branched in Task 4's first step from main), `cp templates/change.md .crs/skipan-mvp.md`, fill, `ws cr skipan "feat: crew board MVP — flags, forecast, suggest, verify, apply" .crs/skipan-mvp.md`. Then review triage per the established policy (reply only reject-with-cause/creative-fix; CodeRabbit self-resolves; Copilot bare-resolves), one fix wave, single re-push.
- [ ] **Step 6:** After merge: flip the ghcr `skipan` package public (org → Packages → skipan → settings, or `ws gh api --method PATCH orgs/SiliconSaga/packages/container/skipan --field visibility=public`).

### Task 15: k8s base + deploy + live smoke (gated: CR merged, sheets seeded)

**Files:**
- Create: `components/skipan/k8s/base/{kustomization,namespace,serviceaccount,configmap,deployment,service,httproute}.yaml`

- [ ] **Step 1:** Manifests — identical shapes to Skipta's `k8s/base` with these substitutions: name/ns/labels `skipan`; KSA `skipan-sa` annotated to `skipan-gsa@teralivekubernetes.iam.gserviceaccount.com`; image `ghcr.io/siliconsaga/skipan:latest`; ConfigMap `skipan-config` data: `gcp_project_id: "teralivekubernetes"`, `gcp_region: "us-east1"`, `board_sheet_id: "<from user>"`, `skipta_sheet_id: "<Skipta's known id>"`, `base_url: "https://skipan.cmdbee.org"`, `rain_threshold: "50"`, `lookback_days: "14"`; Deployment env maps each to `GCP_PROJECT_ID`, `GCP_REGION`, `SKIPAN_BOARD_SHEET_ID`, `SKIPAN_SKIPTA_SHEET_ID`, `SKIPAN_BASE_URL`, `SKIPAN_RAIN_THRESHOLD`, `SKIPAN_LOOKBACK_DAYS`; resources requests 100m/256Mi limits 250m/512Mi (no WeasyPrint); probes on `/healthz`; HTTPRoute host `skipan.cmdbee.org` on `traefik-gateway` web+websecure (wildcard cert, no Certificate/ReferenceGrant).
- [ ] **Step 2:** Extend the session guard: `ws k8s scope set --context gke_teralivekubernetes_us-east1-d_ttf-cluster --namespace skipta,skipan`
- [ ] **Step 3:** `ws k8s create namespace skipan`, then `ws k8s apply -k components/skipan/k8s/base -n skipan`, then `ws k8s rollout status deployment/skipan -n skipan --timeout=120s`.
- [ ] **Step 4:** `curl -s https://skipan.cmdbee.org/healthz` → `{"status":"healthy"}`.
- [ ] **Step 5: Live smoke (the day-2/day-3 beats):** open the board on a phone for the seeded date — the Rasmus site shows the REAL signed amendment flag from the live Skipta sheet and a real forecast badge; tap Suggest → verified plan with reasons; Apply → sheet rows move; set condition override `rain` → re-suggest → warehouse redirection proposed. Negative: suggest with an empty Assignments date (plan proposes nothing or unassigned-fills, verifier holds); break a lat to confirm `unknown` badge.
- [ ] **Step 6:** README "Verified" line (current-state phrasing), commit, fold into the close-out push; update the Thalamus arc; clean the temp `ecosystem.local.yaml` entry post-realm-merge.

---

## Self-review notes

- Spec coverage: data model + short-row padding (T5/T6), weather + override + soft-fail (T7, resolution order pinned by test), amendment bus + lookback + soft-fail (T8, T11), verifier semantics incl. empty-from-unassigned + duplicate + coverage warnings (T9), one-call planner + never-invent prompt + fallback (T10), board render + condition endpoint + degradation notices (T11), suggest/apply contracts incl. re-verify + 422-nothing-applied + 502 (T12), UI tap flow (T13), identity/deploy/catalog-info/recipe (T1/T3/T14/T15). Deferred list untouched.
- Type consistency spot-checks: `VerifiedMove.as_dict()` keys match the route JSON asserted in T12 tests; `apply_moves` consumes `{person_id, to_site}` exactly as the apply route emits; `FakeSheets.stores` access pattern in tests matches T5's fake; conftest overrides match provider names in T11; `Plan.model_copy` usage in T12 test mirrors pydantic v2.
- Judgment calls encoded: board.html ships in T11 (routes need a template to render — T13 only adds controls); weather only for outdoor sites with coords, override still applies to others via the `elif override` branch; suggest returns warnings non-blocking while apply blocks only on invalid moves; single-letter column math in the fake is documented as A..H-sufficient.
