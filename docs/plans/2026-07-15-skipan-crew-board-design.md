# Skipan — Crew Board: AI-Suggested Scheduling & Redirection (Design)

**Date:** 2026-07-15 · **Status:** approved design, pre-implementation · **Component:** `skipan` (new, Tier 3) · **Sibling:** `skipta` (the live field-amendments service)

**Skipan** is Old Norse for arrangement, order, disposition — the act of putting things in their places. Beside Skipta ("the exchange") it forms the pair: an amendment changes the work, Skipan rearranges the people. It is the day-2 beat of the three-day demo story: a signed amendment balloons one site's scope, the dispatcher opens the board, sees the fallout, taps "suggest a plan," and Gemini proposes a crew rearrangement — with reasons — that a human reviews and applies.

This is a demo-tier showcase in the established posture: no auth, keyless Workload Identity, sheet-is-the-database, honest failures, phone-first. Deciding lens from the Leidangr exploration: crew assignments are high-churn operational state, so Skipan is a **standalone service that Backstage will later reflect, never a Backstage plugin holding live state**.

## Goals

- A phone-first day board at `https://skipan.cmdbee.org`: sites, assigned crew members, per-site weather, and amendment fallout flags — live against real Sheets, Skipta's real amendments, and a real forecast.
- One-tap "suggest a plan": a single Gemini structured-output call proposes moves with reasons; a deterministic verifier gates every move; nothing writes until the dispatcher accepts.
- Zero coupling changes to live Skipta: its Amendments sheet **is** the integration bus (read-only).
- The sports-league skin is a data swap: a different spreadsheet (teams/fields/lineups) behind the same config keys — no code change.

## Non-goals (this phase)

- No inventory/warehouse model (Track B — likely a later enrichment on indoor-only logistics sites or a sibling service).
- No Leidangr entity provider or live catalog sync — but the repo ships a `catalog-info.yaml` Component entry from day one so the future reflection is file-cheap.
- No muster-call/issue integration, no auth, no push/webhooks, no persisted plan history (a plan is a transient proposal; only applied assignments persist).

## Data model (one new spreadsheet, four tabs)

- `Crews`: `person_id`, `name`, `crafts` (csv, the Guildhall craft vocabulary doing real work), `crew`
- `Sites`: `site_id`, `customer_name`, `address`, `lat`, `lon`, `site_needs` (csv of `indoor`/`outdoor`, one or both; blank defaults to `outdoor` — a warehouse is an indoor-only site with a logistics job), `needed_crafts` (csv), `notes`, `job_name` (optional card headline; falls back to `customer_name`, then `site_id`)
- `Assignments` (the board state): `date`, `person_id`, `site_id`, `note` — one row per person per date
- `Days`: `date`, `condition_override` (empty | `clear` | `rain` | …), `note` — the demo control; an override always beats the forecast

The human creates and seeds the spreadsheet and shares it Editor with `skipan-gsa`; Skipta's existing spreadsheet is shared **Viewer**. Short rows read padded (the Sheets API truncates trailing empties — same discipline as Skipta).

## Flow and API

| Route | Behavior |
|---|---|
| `GET /` (`?date=YYYY-MM-DD`, default today) | Server-rendered board: one card per site with assigned people and needed-vs-present craft chips; weather badge per `outdoor` site; amendment flags |
| `POST /api/v1/suggest` `{date}` | Assemble compact JSON context → one Gemini structured call → `{moves: [{person_id, from_site, to_site, reason}], summary}` → verifier annotates each move `valid` / `invalid + issues[]` → returned for display. **No write.** |
| `POST /api/v1/apply` `{date, moves}` | Verifier re-runs server-side (never trust the echo); valid moves update `Assignments` rows; any invalid move → 422 with the issues, nothing applied |
| `POST /api/v1/condition` `{date, condition}` | Writes the `Days` override — the deterministic demo lever |
| `GET /healthz` | Probe target |

**Amendment flags:** on board load, Skipan reads Skipta's `Amendments` tab (read-only), filters `status=signed, kind=amend` rows within a configurable lookback window, matches `customer_name` to `Sites.customer_name`, and renders "scope +$`total` — `proposal_name`" on the affected site card. The same deltas ride into the suggest context as site-demand changes.

**Weather:** open-meteo daily forecast (keyless, free) per site `lat`/`lon` for the board date; precipitation probability ≥ threshold → `rain-risk`. Resolution order: `Days.condition_override` > forecast > `clear`. Rain-risk on `outdoor` sites feeds the suggest context ("outdoor work at risk — consider redirecting to indoor/warehouse sites"), producing the day-3 beat.

## The suggest pipeline (Gemini plans, verifier gates)

One structured-output call (`PLAN_SCHEMA`: `moves[]` of `{person_id, from_site, to_site, reason}` + `summary`; same model fallback chain and cost caps as Skipta). The prompt carries the never-invent discipline: move only people listed in the context, only between listed sites, prefer craft matches, explain every move in one sentence.

The **verifier** is the UNMATCHED sibling — pure functions, no I/O:

- `person_id` exists in Crews; `from_site` matches the person's current assignment (empty `from_site` is valid exactly when the person has no assignment row that date — applying then inserts a row instead of updating one); `to_site` exists in Sites (a warehouse is just an indoor-only site, no special case)
- No person ends the day double-booked after the full move-set is applied
- Craft coverage: for each site, `needed_crafts` vs post-move present crafts — gaps annotate the move-set as warnings (visible, non-blocking); nonexistent people/sites mark the move `invalid` (blocking)

Invalid moves render struck-through with their issues; the dispatcher applies only the valid remainder (or none). `apply` re-verifies server-side before any write.

## Module map

| Module | Purpose | Depends on |
|---|---|---|
| `app/main.py` | routes only | all below |
| `app/config.py` | env: board sheet id, Skipta sheet id, model chain, weather threshold, lookback days, base URL | — |
| `app/google_clients.py` | credentials, Sheets service, model factory (lifted Skipta pattern) | ADC/WI |
| `app/board.py` | Crews/Sites/Assignments/Days reads + `apply_moves` writes | Sheets |
| `app/amendments_feed.py` | read-only Skipta Amendments → site flags + demand deltas | Sheets (Viewer) |
| `app/weather.py` | open-meteo via injectable HTTP client; condition resolution | open-meteo |
| `app/planner.py` | context builder + Gemini structured call (`PLAN_SCHEMA`) | Vertex AI |
| `app/verifier.py` | pure move validation + craft-coverage analysis | — |
| `app/templates/board.html` + vendored static | phone-first board UI | — |

All clients constructed in one place and injected; tests swap fakes without patching.

## Identity and deployment (the oiled recipe)

New `skipan-gsa` (`roles/aiplatform.user`, WI binding `skipan/skipan-sa`, `tokenCreator` for the human); no Drive, no GCS — Skipan owns nothing but sheet rows. Repo `SiliconSaga/skipan` with the phase-1 scaffold (Makefile venv-detection, requirements pins incl. the `<1.160` aiplatform cap, ruff/pytest, `.env.template`); realm tier-3 entry + `make`-based adapter; Actions `ci` + `image` → ghcr; kustomize base (ns `skipan`, annotated KSA, ConfigMap of identifiers, Deployment with `/healthz` probes, ClusterIP, HTTPRoute `skipan.cmdbee.org` on the platform wildcard); session guard scope extended to cover the `skipan` namespace at deploy time. `catalog-info.yaml` ships in-repo: a `Component` (`spec.type: service`) owned per the Leidangr conventions, inert until Track D.

## Error handling

| Failure | Response |
|---|---|
| Gemini plan fails schema after fallback chain | 502 "could not draft a plan" — board stays usable manually |
| Verifier finds invalid moves in `apply` | 422 with per-move issues; nothing applied |
| open-meteo unreachable/timeout | Weather badge renders `unknown`; board loads; suggest context says conditions unknown |
| Skipta sheet unreadable | Amendment flags omitted with a visible notice; board loads |
| Board sheet unreachable | Honest 502 (it is the database) |
| Unknown date format / person / site in requests | 422 |

Degradation posture: only the board sheet is load-bearing; every enrichment (weather, amendments, AI) fails soft and visibly.

## Testing

TDD with the established fake-injection pattern: `FakeSheets` (Skipta's shape, two spreadsheets routed by id), fake HTTP for open-meteo (canned forecasts), fake model for the planner (canned valid plan, hallucinated-person plan, double-booking plan, garbage → fallback → 502). `verifier.py` is pure-unit. Routes under TestClient with all fakes. Live smoke: seed real sheets, open the board on a phone, flag from the real signed Rasmus amendment, suggest → apply, rain-override → warehouse redirect suggestion.

## Deferred

- Track B inventory (warehouse work content beyond "redirect people to the warehouse site").
- Track C Leidangr GKE deploy (parallel, human-gated, own session) and Track D demo assembly (Saga narrative + Cycle container + walkthrough) — Skipan only pre-stages `catalog-info.yaml`.
- Sports-league spreadsheet skin (data swap validation), muster-call issue integration, auth, plan history/audit trail, webhooks.
- Site-to-site navigation in the planner context: the availability ramp is haversine straight-line from the existing Sites lat/lon (free, zero deps) → OSRM road distance/time (keyless demo server or self-hosted with OSM data) → live traffic and road closures (commercial APIs only — also the first feature that would force an API-key Secret into the posture). Pursue in that order, and only when a schedule decision actually hinges on travel.
