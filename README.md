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
