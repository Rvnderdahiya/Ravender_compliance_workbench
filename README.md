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

## Step 1 scope (current)

- Single-screen UI only
- Request intake for `Person` or `Company`
- Google depth selection (`1`, `2`, or `3` pages)
- Optional photo-check flag
- Approved-domain and blocked-domain lists are editable in UI
- Automatic creation of a request folder on local machine

Each request folder includes:

- `request.json`
- `notes/summary.txt`
- empty `pdf/` and `screenshots/` folders for the next execution step

## Local folders

- App state: `runtime_data/workbench_state.json`
- V1 request workspace: `C:\Users\<you>\Documents\AMEX_Compliance_Evidence_Desk_V1\requests`
- Archived previous UI: `archive/v0_6_multitab_ui/static`

## Next step

Step 2 will execute the search workflow itself:

- run Google query
- scan up to selected page depth
- filter blocked domains
- open valid matches
- save screenshots/PDF evidence into each request folder
