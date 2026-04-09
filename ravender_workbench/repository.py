from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from threading import RLock

from ravender_workbench.public_web import investigate_public_website


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def normalize_source_url(url: str) -> str:
    cleaned = str(url or "").strip()
    if not cleaned:
        raise ValueError("Site URL is required.")
    if " " in cleaned:
        raise ValueError("Site URL cannot contain spaces.")
    if not cleaned.lower().startswith(("http://", "https://")):
        cleaned = f"https://{cleaned}"
    return cleaned


@dataclass
class WorkbenchRepository:
    engine: object
    state_path: Path | None = None

    def __post_init__(self) -> None:
        self._lock = RLock()
        self.state_path = Path(self.state_path) if self.state_path else None
        self._state = self._load_state()

    def _load_state(self) -> dict:
        seed = self._build_seed_state()
        if not self.state_path or not self.state_path.exists():
            return seed

        try:
            loaded = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return seed

        if not isinstance(loaded, dict):
            return seed

        return self._normalize_state(loaded, seed)

    def _normalize_state(self, loaded: dict, seed: dict) -> dict:
        state = deepcopy(seed)

        for key in ("product", "sources", "packs", "cases", "blueprint"):
            if isinstance(loaded.get(key), type(seed[key])):
                state[key] = loaded[key]

        state["product"]["name"] = seed["product"]["name"]
        state["product"]["version"] = seed["product"]["version"]
        state["product"]["tagline"] = seed["product"]["tagline"]
        state["product"]["engine"] = seed["product"]["engine"]
        state["product"]["hostingMode"] = seed["product"]["hostingMode"]

        loaded_investigator = loaded.get("publicInvestigator", {})
        investigator = state["publicInvestigator"]
        if isinstance(loaded_investigator, dict):
            form = loaded_investigator.get("form", {})
            if isinstance(form, dict):
                investigator["form"]["url"] = str(form.get("url") or investigator["form"]["url"])
                investigator["form"]["query"] = str(form.get("query") or investigator["form"]["query"])
                investigator["form"]["maxPages"] = int(form.get("maxPages") or investigator["form"]["maxPages"])

            if isinstance(loaded_investigator.get("recentRuns"), list):
                investigator["recentRuns"] = loaded_investigator["recentRuns"][:8]
            if isinstance(loaded_investigator.get("runs"), list):
                investigator["runs"] = loaded_investigator["runs"][:8]
            if loaded_investigator.get("latestRun"):
                investigator["latestRun"] = loaded_investigator["latestRun"]
                if not investigator["runs"]:
                    investigator["runs"] = [loaded_investigator["latestRun"]]

        loaded_builder = loaded.get("sourceBuilder", {})
        builder = state["sourceBuilder"]
        if isinstance(loaded_builder, dict):
            form = loaded_builder.get("form", {})
            if isinstance(form, dict):
                for key in ("name", "siteUrl", "sourceType", "description", "owner"):
                    if key in form:
                        builder["form"][key] = str(form.get(key) or builder["form"][key])
            if isinstance(loaded_builder.get("drafts"), list):
                builder["drafts"] = loaded_builder["drafts"][:12]

        return state

    def _persist_state(self) -> None:
        if not self.state_path:
            return

        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.state_path.with_suffix(f"{self.state_path.suffix}.tmp")
        temp_path.write_text(json.dumps(self._state, indent=2), encoding="utf-8")
        temp_path.replace(self.state_path)

    def _build_seed_state(self) -> dict:
        return {
            "product": {
                "name": "Ravender Workbench",
                "version": "0.4.0",
                "tagline": "Case-first investigations for analysts, with website investigation and source-definition workflows.",
                "engine": getattr(self.engine, "name", "unknown"),
                "hostingMode": "Single machine pilot",
            },
            "sources": [
                {
                    "id": "public_adverse_media",
                    "name": "Public Adverse Media",
                    "category": "Public web",
                    "authModel": "No login",
                    "executionMode": "Direct replay when stable",
                    "approvalState": "Certified",
                },
                {
                    "id": "griffin_profile",
                    "name": "Griffin Profile Lookup",
                    "category": "Internal portal",
                    "authModel": "Managed browser session",
                    "executionMode": "Browser-backed",
                    "approvalState": "Certified",
                },
                {
                    "id": "cadence_activity",
                    "name": "Cadence Activity Lookup",
                    "category": "Internal portal",
                    "authModel": "Managed browser session",
                    "executionMode": "Browser-backed",
                    "approvalState": "Pilot",
                },
                {
                    "id": "sanctions_screening",
                    "name": "Sanctions Open-Web Screening",
                    "category": "Public web",
                    "authModel": "No login",
                    "executionMode": "Direct replay when stable",
                    "approvalState": "Draft",
                },
            ],
            "packs": [
                {
                    "id": "retail-edd-v1",
                    "name": "Retail EDD",
                    "version": "1.0",
                    "status": "Published",
                    "owner": "Compliance Automation",
                    "description": "Public web adverse media plus Griffin and Cadence review for retail cases.",
                    "inputs": ["Case ID", "Subject name", "DOB", "Country"],
                    "steps": [
                        "Search approved public sources",
                        "Open Griffin customer profile",
                        "Open Cadence activity history",
                        "Normalize evidence into analyst cards",
                    ],
                    "controls": [
                        "Read-only execution",
                        "Source allowlist enforced",
                        "Evidence retained with timestamp",
                        "Reviewer sign-off required for publication",
                    ],
                },
                {
                    "id": "griffin-cadence-basic-v1",
                    "name": "Griffin + Cadence Basic",
                    "version": "1.3",
                    "status": "Published",
                    "owner": "Compliance Automation",
                    "description": "Fast internal-portal lookup pack for existing-customer reviews.",
                    "inputs": ["Case ID", "Subject name", "Country"],
                    "steps": [
                        "Search Griffin for the matching customer",
                        "Collect core profile fields",
                        "Open Cadence activity",
                        "Produce evidence summary for disposition",
                    ],
                    "controls": [
                        "Managed browser session only",
                        "No write actions",
                        "Session timeout handoff supported",
                        "Audit event appended after each run",
                    ],
                },
                {
                    "id": "public-screening-v2",
                    "name": "Public Screening",
                    "version": "2.0",
                    "status": "Draft",
                    "owner": "Compliance Innovation",
                    "description": "Open-web pilot pack for quick external context capture.",
                    "inputs": ["Subject name", "Country"],
                    "steps": [
                        "Run certified public searches",
                        "Collect article and people-search evidence",
                        "Mark ambiguous hits for analyst review",
                    ],
                    "controls": [
                        "Public domains only",
                        "No login reuse",
                        "Analyst review required before submission",
                    ],
                },
            ],
            "cases": [
                {
                    "id": "KYC-2026-004218",
                    "subject": "John A Doe",
                    "dob": "1986-02-14",
                    "country": "US",
                    "lineOfBusiness": "Retail Banking",
                    "riskLevel": "High",
                    "status": "Ready to run",
                    "selectedPackId": "retail-edd-v1",
                    "summary": "No certified pack has been run yet for this review.",
                    "recommendedDecision": "Pending",
                    "decision": "",
                    "notes": "",
                    "tasks": [
                        {
                            "sourceId": "public_adverse_media",
                            "label": "Public Web Adverse Media",
                            "status": "Not started",
                            "hits": 0,
                            "evidenceCount": 0,
                            "lastRun": "Pending",
                            "actionLabel": "Run pack",
                            "mode": "Awaiting execution",
                        },
                        {
                            "sourceId": "griffin_profile",
                            "label": "Griffin Customer Lookup",
                            "status": "Not started",
                            "hits": 0,
                            "evidenceCount": 0,
                            "lastRun": "Pending",
                            "actionLabel": "Run pack",
                            "mode": "Awaiting execution",
                        },
                        {
                            "sourceId": "cadence_activity",
                            "label": "Cadence Activity Lookup",
                            "status": "Not started",
                            "hits": 0,
                            "evidenceCount": 0,
                            "lastRun": "Pending",
                            "actionLabel": "Run pack",
                            "mode": "Awaiting execution",
                        },
                    ],
                    "evidence": [],
                    "auditTrail": [
                        {
                            "time": "2026-04-09 16:55 UTC",
                            "actor": "System",
                            "message": "Case created and waiting for a certified Search Pack run.",
                        }
                    ],
                },
                {
                    "id": "KYC-2026-004231",
                    "subject": "Maria Chen",
                    "dob": "1991-09-03",
                    "country": "SG",
                    "lineOfBusiness": "Global Commercial Services",
                    "riskLevel": "Medium",
                    "status": "Ready to run",
                    "selectedPackId": "griffin-cadence-basic-v1",
                    "summary": "Existing-customer review ready for a certified internal lookup.",
                    "recommendedDecision": "Pending",
                    "decision": "",
                    "notes": "",
                    "tasks": [
                        {
                            "sourceId": "griffin_profile",
                            "label": "Griffin Customer Lookup",
                            "status": "Not started",
                            "hits": 0,
                            "evidenceCount": 0,
                            "lastRun": "Pending",
                            "actionLabel": "Run pack",
                            "mode": "Awaiting execution",
                        },
                        {
                            "sourceId": "cadence_activity",
                            "label": "Cadence Activity Lookup",
                            "status": "Not started",
                            "hits": 0,
                            "evidenceCount": 0,
                            "lastRun": "Pending",
                            "actionLabel": "Run pack",
                            "mode": "Awaiting execution",
                        },
                    ],
                    "evidence": [],
                    "auditTrail": [
                        {
                            "time": "2026-04-09 17:02 UTC",
                            "actor": "Queue manager",
                            "message": "Case routed to analyst workbench for same-day review.",
                        }
                    ],
                },
                {
                    "id": "KYC-2026-004244",
                    "subject": "Acme Fabrication LLC",
                    "dob": "N/A",
                    "country": "US",
                    "lineOfBusiness": "Merchant Services",
                    "riskLevel": "Low",
                    "status": "In review",
                    "selectedPackId": "public-screening-v2",
                    "summary": "Draft public-web pack can be explored in admin mode only.",
                    "recommendedDecision": "Needs Review",
                    "decision": "",
                    "notes": "Hold until public-screening-v2 is certified.",
                    "tasks": [
                        {
                            "sourceId": "public_adverse_media",
                            "label": "Public Web Adverse Media",
                            "status": "Draft pack only",
                            "hits": 0,
                            "evidenceCount": 0,
                            "lastRun": "Not eligible",
                            "actionLabel": "Use certified pack",
                            "mode": "Blocked by governance",
                        }
                    ],
                    "evidence": [],
                    "auditTrail": [
                        {
                            "time": "2026-04-09 17:11 UTC",
                            "actor": "Reviewer",
                            "message": "Draft pack blocked from analyst use until certification is complete.",
                        }
                    ],
                },
            ],
            "publicInvestigator": {
                "form": {
                    "url": "https://www.python.org/",
                    "query": "download, docs, psf",
                    "maxPages": 6,
                },
                "presets": [
                    {
                        "label": "Python",
                        "url": "https://www.python.org/",
                        "query": "download, docs, psf",
                    },
                    {
                        "label": "Wikipedia",
                        "url": "https://en.wikipedia.org/wiki/Artificial_intelligence",
                        "query": "machine learning, research, ethics",
                    },
                    {
                        "label": "Example",
                        "url": "https://example.com/",
                        "query": "illustrative domain",
                    },
                ],
                "capabilities": [
                    "Crawl same-site public HTML pages",
                    "Follow discovered links and sitemap URLs",
                    "Extract page titles, descriptions, headings, emails, and phones",
                    "Match analyst query terms and generate snippets",
                    "Export investigation output as JSON from the UI",
                ],
                "limits": [
                    "Authenticated portals are out of scope for this mode",
                    "Heavy JavaScript-only content may be incomplete",
                    "CAPTCHA and anti-bot protected sites may not be accessible",
                    "The page cap is intentional for speed and safety",
                ],
                "recentRuns": [],
                "runs": [],
                "latestRun": None,
            },
            "sourceBuilder": {
                "form": {
                    "name": "",
                    "siteUrl": "",
                    "sourceType": "Public website",
                    "description": "",
                    "owner": "Compliance Automation",
                },
                "sourceTypes": ["Public website", "Login website", "Internal portal"],
                "drafts": [],
                "workflow": [
                    "Add New Source",
                    "Record Steps",
                    "Map Inputs",
                    "Define Extraction Rules",
                    "Test",
                    "Publish",
                ],
                "notes": [
                    "This first slice saves source definitions locally as drafts.",
                    "Recording, input mapping, testing, and publishing will be enabled in the next steps.",
                ],
            },
            "blueprint": {
                "principles": [
                    "Analysts learn the UI, not automation internals.",
                    "Every source must be certified before analyst use.",
                    "All execution is read-only in phase 1.",
                    "Each run must leave an evidence and audit trail.",
                ],
                "phases": [
                    {
                        "name": "Pilot",
                        "focus": "Single-machine demo with certified mock packs",
                        "outcome": "Validate analyst UX and source workflow",
                    },
                    {
                        "name": "Platform",
                        "focus": "Workflow-service integration, persistence, SSO, and RBAC",
                        "outcome": "Controlled internal testing with real sources",
                    },
                    {
                        "name": "Enterprise",
                        "focus": "Session broker, reviewer queues, health checks, and reporting",
                        "outcome": "Production-ready compliance search operations",
                    },
                ],
                "controls": [
                    "Source allowlist",
                    "Role-based access",
                    "Maker-checker for pack publication",
                    "Retention and evidence export",
                    "Session timeout recovery",
                ],
            },
        }

    def _find_case(self, case_id: str) -> dict:
        for case in self._state["cases"]:
            if case["id"] == case_id:
                return case
        raise KeyError(f"Case not found: {case_id}")

    def _find_pack(self, pack_id: str) -> dict:
        for pack in self._state["packs"]:
            if pack["id"] == pack_id:
                return pack
        raise KeyError(f"Pack not found: {pack_id}")

    def _build_stats(self) -> list[dict]:
        cases = self._state["cases"]
        packs = self._state["packs"]
        sources = self._state["sources"]
        public_runs = self._state["publicInvestigator"]["recentRuns"]
        builder_drafts = self._state["sourceBuilder"]["drafts"]
        ready_cases = sum(1 for case in cases if case["status"] in {"Ready to run", "Ready for analyst review"})
        published_packs = sum(1 for pack in packs if pack["status"] == "Published")
        certified_sources = sum(1 for source in sources if source["approvalState"] == "Certified")
        return [
            {"label": "Cases ready", "value": str(ready_cases)},
            {"label": "Published packs", "value": str(published_packs)},
            {"label": "Certified sources", "value": str(certified_sources)},
            {"label": "Website runs", "value": str(len(public_runs))},
            {"label": "Draft sources", "value": str(len(builder_drafts))},
        ]

    def get_bootstrap(self) -> dict:
        with self._lock:
            payload = deepcopy(self._state)
            payload["stats"] = self._build_stats()
            payload["serverTime"] = utc_now()
            return payload

    def run_pack(self, case_id: str, pack_id: str) -> dict:
        with self._lock:
            case = self._find_case(case_id)
            pack = self._find_pack(pack_id)
            result = self.engine.run_pack(case, pack)

            case["selectedPackId"] = pack_id
            case["tasks"] = result["tasks"]
            case["evidence"] = result["evidence"]
            case["summary"] = result["summary"]
            case["recommendedDecision"] = result["recommendedDecision"]
            case["status"] = "Ready for analyst review"
            case["auditTrail"].insert(0, result["auditEvent"])
            self._persist_state()

            return {"ok": True, "case": deepcopy(case), "message": "Certified pack executed."}

    def save_decision(self, case_id: str, decision: str, notes: str) -> dict:
        with self._lock:
            case = self._find_case(case_id)
            case["decision"] = decision
            case["notes"] = notes
            case["status"] = "Submitted for review"
            case["auditTrail"].insert(
                0,
                {
                    "time": utc_now(),
                    "actor": "Analyst",
                    "message": f"Decision submitted: {decision}.",
                },
            )
            self._persist_state()
            return {"ok": True, "case": deepcopy(case), "message": "Decision submitted for reviewer queue."}

    def resume_source(self, case_id: str, source_id: str) -> dict:
        with self._lock:
            case = self._find_case(case_id)
            result = self.engine.resume_source(case, source_id)
            task_update = result.get("taskUpdate")
            if task_update:
                for index, task in enumerate(case["tasks"]):
                    if task["sourceId"] == source_id:
                        case["tasks"][index] = task_update
                        break
                case["evidence"].extend(result.get("evidence", []))
                case["summary"] = "All source steps are now complete and ready for disposition."
                case["recommendedDecision"] = "Needs Review"
            case["auditTrail"].insert(
                0,
                {
                    "time": utc_now(),
                    "actor": "Analyst",
                    "message": result.get("message", "Source resumed."),
                },
            )
            self._persist_state()
            return {"ok": True, "case": deepcopy(case), "message": result.get("message", "Source resumed.")}

    def run_public_investigation(self, url: str, query: str, max_pages: int) -> dict:
        with self._lock:
            investigator = self._state["publicInvestigator"]
            result = investigate_public_website(url=url, query=query, max_pages=max_pages)

            investigator["form"] = {
                "url": url,
                "query": query,
                "maxPages": max_pages,
            }
            investigator["latestRun"] = result
            investigator["runs"] = [run for run in investigator.get("runs", []) if run.get("id") != result["id"]]
            investigator["runs"].insert(0, result)
            investigator["runs"] = investigator["runs"][:8]
            investigator["recentRuns"].insert(
                0,
                {
                    "id": result["id"],
                    "domain": result["domain"],
                    "targetUrl": result["targetUrl"],
                    "queryTerms": result["queryTerms"],
                    "pagesCrawled": result["pagesCrawled"],
                    "matchedPages": result["matchedPages"],
                    "completedAt": result["completedAt"],
                    "summary": result["summary"],
                },
            )
            investigator["recentRuns"] = investigator["recentRuns"][:8]
            self._persist_state()

            return {
                "ok": True,
                "investigation": deepcopy(result),
                "recentRuns": deepcopy(investigator["recentRuns"]),
                "message": f"Public investigation completed for {result['domain']}.",
            }

    def save_source_draft(
        self,
        *,
        name: str,
        site_url: str,
        source_type: str,
        description: str,
        owner: str,
    ) -> dict:
        with self._lock:
            builder = self._state["sourceBuilder"]
            allowed_types = set(builder["sourceTypes"])
            cleaned_name = str(name or "").strip()
            cleaned_owner = str(owner or "").strip() or "Compliance Automation"
            cleaned_type = str(source_type or "").strip()
            cleaned_description = str(description or "").strip()
            normalized_url = normalize_source_url(site_url)

            if not cleaned_name:
                raise ValueError("Source name is required.")
            if cleaned_type not in allowed_types:
                raise ValueError("A valid source type is required.")

            duplicate = next(
                (
                    draft
                    for draft in builder["drafts"]
                    if draft["name"].lower() == cleaned_name.lower() and draft["siteUrl"].lower() == normalized_url.lower()
                ),
                None,
            )
            timestamp = utc_now()
            if duplicate:
                duplicate["sourceType"] = cleaned_type
                duplicate["description"] = cleaned_description
                duplicate["owner"] = cleaned_owner
                duplicate["updatedAt"] = timestamp
                draft_record = duplicate
            else:
                draft_record = {
                    "id": f"source-{int(datetime.now(timezone.utc).timestamp() * 1000)}",
                    "name": cleaned_name,
                    "siteUrl": normalized_url,
                    "sourceType": cleaned_type,
                    "description": cleaned_description,
                    "owner": cleaned_owner,
                    "status": "Draft",
                    "recordingStatus": "Not started",
                    "testStatus": "Not run",
                    "publishStatus": "Not published",
                    "createdAt": timestamp,
                    "updatedAt": timestamp,
                }
                builder["drafts"].insert(0, draft_record)
                builder["drafts"] = builder["drafts"][:12]

            builder["form"] = {
                "name": "",
                "siteUrl": "",
                "sourceType": builder["sourceTypes"][0],
                "description": "",
                "owner": cleaned_owner,
            }
            self._persist_state()
            return {
                "ok": True,
                "draft": deepcopy(draft_record),
                "sourceBuilder": deepcopy(builder),
                "message": f'Source draft saved for {cleaned_name}.',
            }
