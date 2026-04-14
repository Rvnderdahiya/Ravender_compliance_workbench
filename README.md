# AMEX Compliance Evidence Desk

Version 1 is now intentionally simplified to one workflow:

- create a daily Google-search request
- keep social and non-authorized domains blocked
- generate a dedicated local folder per request for evidence work

## Run

```powershell
cd <repo-folder>
python app.py
```

Open [http://127.0.0.1:8080](http://127.0.0.1:8080).

## Current scope

- Single-screen UI only
- Request intake for `Person` or `Company`
- Google depth selection (`1`, `2`, or `3` pages)
- Optional photo-check flag
- Approved-domain and blocked-domain lists are editable in UI
- Automatic creation of a request folder on local machine
- Run Search action from queue:
  - scans Google pages 1-3
  - uses Bing RSS fallback (and then DuckDuckGo HTML fallback only if needed)
  - filters blocked and non-approved domains
  - evaluates approved candidate pages for match strength
  - saves PDFs/screenshots only for successful matches (no generic search-page digest capture)
  - captures up to first 5 successful pages per run for predictable runtime
  - flags photo presence when page images exist
  - writes `notes/pdf_index.txt` and `notes/pdf_index.csv` that map each saved PDF to URL, title, and match reason
  - saves `run_summary.json` and `run_summary.txt`
  - attempts PDF/screenshot capture using local headless browser (if available)
  - shows run metrics on each queue card

Each request folder includes:

- `request.json`
- `notes/summary.txt`
- empty `pdf/` and `screenshots/` folders for the next execution step

## Local folders

- App state: `runtime_data/workbench_state.json`
- V1 request workspace: `C:\Users\<you>\Documents\AMEX_Compliance_Evidence_Desk_V1\requests`
- Archived previous UI: `archive/v0_6_multitab_ui/static`

## Next step

Step 3 will improve execution quality and analyst controls:

- stronger exact-match rules for person/company details
- configurable approved-domain profiles by use case
- clearer per-result action panel (open link, open artifact, mark manual photo review)
