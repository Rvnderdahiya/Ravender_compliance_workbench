# Ravender Workbench

Case-first compliance search orchestration for non-technical analysts, with a Website Investigator for analysts and a Source Builder for admins.

This repository is a stronger pilot build for an enterprise-friendly compliance workbench built around a reusable workflow-engine pattern. It is designed to be:

- easy for analysts to learn
- safe to demo on a single machine
- immediately useful for live public-website investigations
- ready to evolve into a real Griffin and Cadence search runner
- structured so we can swap the mock engine for a live workflow service later

## What is in this first version

- Analyst workbench UI
- Website Investigator for live public-website crawling and term matching
- Source Builder with draft source definitions and guided recorded-step capture
- Search Pack Studio for admins
- Governance and rollout views
- Local JSON-backed state so recent runs survive app restarts on one machine
- Mock automation engine with a clear live-service adapter seam
- Zero third-party Python dependencies

## Run it

```powershell
cd C:\Users\QSS\Documents\Ravender\Web_tool
python app.py
```

Then open [http://127.0.0.1:8080](http://127.0.0.1:8080).

The app stores local pilot state in `runtime_data/workbench_state.json`.

## Demo actions

1. Open the `Website Investigator` tab.
2. Enter any public website URL, add the terms you want to look for, and choose the page cap.
3. Click `Run Live Investigation`.
4. Review matched pages, snippets, contact details, crawl notes, and limitations.
5. Use the recent-run rail to reopen earlier investigations.
6. Export the selected investigation as JSON if you want to share or archive it.

You can also test the case workflow:

1. Open the `Analyst Workbench` tab.
2. Select case `KYC-2026-004218`.
3. Pick a Search Pack.
4. Click `Run Certified Pack`.
5. Review evidence.
6. If a source shows `Needs assist`, click `Resume Source`.
7. Add notes and submit a decision.

You can now test the Source Builder slices:

1. Open the `Source Builder` tab.
2. Fill `Source name`, `Site URL`, `Source type`, `Owner`, and `Short description`.
3. Click `Save Draft Source`.
4. Confirm the draft appears in the left rail and survives a refresh.
5. Select the draft and click `Launch Site`.
6. Click `Start Recording`.
7. Add recorded steps one by one using `Action type`, `Target label`, `Selector hint`, `Value`, and `Notes`.
8. Click `Pause`, `Stop`, and `Save Recording`.

## Repo structure

```text
app.py
ravender_workbench/
  engine.py
  public_web.py
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

1. Keep expanding the public-website mode with richer extraction, screening packs, and evidence controls.
2. Replace the mock engine with a live workflow adapter.
3. Persist cases, packs, evidence, and audit events in enterprise storage.
4. Add SSO, RBAC, maker-checker approval, and session brokering.
5. Publish certified Search Packs for Griffin, Cadence, and approved public websites.

## Repository

GitHub:

`Rvnderdahiya/Ravender_compliance_workbench`
