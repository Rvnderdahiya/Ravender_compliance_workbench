# Ravender Workbench

Case-first compliance search orchestration for non-technical analysts.

This repository is the first pilot build for an enterprise-friendly compliance workbench built around a reusable workflow-engine pattern. It is designed to be:

- easy for analysts to learn
- safe to demo on a single machine
- ready to evolve into a real Griffin and Cadence search runner
- structured so we can swap the mock engine for a live workflow service later

## What is in this first version

- Analyst workbench UI
- Search Pack Studio for admins
- Governance and rollout views
- In-memory case queue and evidence model
- Mock automation engine with a clear live-service adapter seam
- Zero third-party Python dependencies

## Run it

```powershell
cd C:\Users\QSS\Documents\Ravender\Web_tool
python app.py
```

Then open [http://127.0.0.1:8080](http://127.0.0.1:8080).

## Demo actions

1. Open the `Analyst Workbench` tab.
2. Select case `KYC-2026-004218`.
3. Pick a Search Pack.
4. Click `Run Certified Pack`.
5. Review evidence.
6. If a source shows `Needs assist`, click `Resume Source`.
7. Add notes and submit a decision.

## Repo structure

```text
app.py
ravender_workbench/
  engine.py
  repository.py
static/
  index.html
  styles.css
  app.js
docs/
  architecture.md
  phase-1-roadmap.md
```

## How this becomes the real product

The current engine is intentionally mocked. The integration seam lives in `ravender_workbench/engine.py`.

Planned production path:

1. Replace the mock engine with a live workflow adapter.
2. Persist cases, packs, evidence, and audit events in enterprise storage.
3. Add SSO, RBAC, maker-checker approval, and session brokering.
4. Publish certified Search Packs for Griffin, Cadence, and approved public websites.

## Repository

GitHub:

`Rvnderdahiya/Ravender_compliance_workbench`
