from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import mimetypes
from pathlib import Path
import re
from threading import RLock

from ravender_workbench.public_web import investigate_public_website
from ravender_workbench.v1_search import run_v1_search_job


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


def sanitize_owner_label(value: str) -> str:
    cleaned = str(value or "").strip()
    if not cleaned or "ravender" in cleaned.lower():
        return "Compliance Operations"
    return cleaned


def blank_source_builder_form(owner: str = "Compliance Operations") -> dict:
    return {
        "name": "",
        "siteUrl": "",
        "sourceType": "Public website",
        "description": "",
        "owner": sanitize_owner_label(owner),
    }


def blank_recording_form() -> dict:
    return {
        "actionType": "Open page",
        "pageName": "",
        "targetLabel": "",
        "selectorHint": "",
        "value": "",
        "notes": "",
    }


def blank_recording_session_form() -> dict:
    return {
        "agendaType": "",
        "goal": "",
        "captureScreenshots": False,
    }


def blank_v1_search_form() -> dict:
    return {
        "subjectType": "Person",
        "subjectName": "",
        "subjectDetails": "",
        "googlePages": 1,
        "photoCheckRequired": False,
    }


def slugify_folder_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", str(value or "").strip()).strip("-").lower()
    return cleaned or "search"


def normalize_domain_entry(value: str) -> str:
    cleaned = str(value or "").strip().lower()
    cleaned = cleaned.removeprefix("http://").removeprefix("https://").strip("/")
    cleaned = cleaned.removeprefix("www.")
    if not cleaned:
        raise ValueError("Domain value is required.")
    if " " in cleaned:
        raise ValueError("Domain value cannot contain spaces.")
    if "." not in cleaned and not cleaned.startswith("."):
        raise ValueError("Domain value should look like a domain, for example example.com or .gov.")
    return cleaned


@dataclass
class WorkbenchRepository:
    engine: object
    state_path: Path | None = None

    def __post_init__(self) -> None:
        self._lock = RLock()
        self.state_path = Path(self.state_path) if self.state_path else None
        self._state = self._load_state()
        self._persist_state()

    def _default_v1_workspace_root(self) -> Path:
        return Path.home() / "Documents" / "AMEX_Compliance_Evidence_Desk_V1" / "requests"

    def _sanitize_v1_output_root(self, value: str) -> str:
        default_root = self._default_v1_workspace_root()
        cleaned = str(value or "").strip()
        if not cleaned:
            return str(default_root)
        lowered = cleaned.lower()
        if "ravender" in lowered:
            return str(default_root)
        try:
            return str(Path(cleaned).expanduser().resolve())
        except OSError:
            return str(default_root)

    def _safe_domain_list(self, entries: list, limit: int = 25) -> list[str]:
        normalized: list[str] = []
        seen = set()
        for entry in entries:
            try:
                cleaned = normalize_domain_entry(entry)
            except ValueError:
                continue
            if cleaned in seen:
                continue
            seen.add(cleaned)
            normalized.append(cleaned)
            if len(normalized) >= limit:
                break
        return normalized

    def _normalize_v1_job(self, job: dict, default_root: str) -> dict:
        approved_source = job.get("approvedDomains")
        if not isinstance(approved_source, list):
            approved_source = job.get("allowedDomainHints") if isinstance(job.get("allowedDomainHints"), list) else []
        summary = job.get("lastRunSummary")
        if not isinstance(summary, dict):
            summary = {}
        return {
            "id": str(job.get("id") or f"v1-{int(datetime.now(timezone.utc).timestamp() * 1000)}"),
            "createdAt": str(job.get("createdAt") or utc_now()),
            "subjectType": str(job.get("subjectType") or "Person"),
            "subjectName": str(job.get("subjectName") or "").strip(),
            "subjectDetails": str(job.get("subjectDetails") or "").strip(),
            "googlePages": max(1, min(int(job.get("googlePages") or 1), 3)),
            "photoCheckRequired": bool(job.get("photoCheckRequired", False)),
            "status": str(job.get("status") or "Request created"),
            "folderPath": str(job.get("folderPath") or default_root),
            "approvedDomains": self._safe_domain_list(approved_source),
            "blockedDomains": self._safe_domain_list(job.get("blockedDomains") or []),
            "requestFilePath": str(job.get("requestFilePath") or ""),
            "summaryFilePath": str(job.get("summaryFilePath") or ""),
            "lastRunAt": str(job.get("lastRunAt") or ""),
            "lastRunSummary": summary,
        }

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
                builder["form"]["owner"] = sanitize_owner_label(builder["form"]["owner"])
            recording_form = loaded_builder.get("recordingForm", {})
            if isinstance(recording_form, dict):
                for key in ("actionType", "pageName", "targetLabel", "selectorHint", "value", "notes"):
                    if key in recording_form:
                        builder["recordingForm"][key] = str(recording_form.get(key) or builder["recordingForm"][key])
            session_form = loaded_builder.get("recordingSessionForm", {})
            if isinstance(session_form, dict):
                if "agendaType" in session_form:
                    builder["recordingSessionForm"]["agendaType"] = str(
                        session_form.get("agendaType") or builder["recordingSessionForm"]["agendaType"]
                    )
                if "goal" in session_form:
                    builder["recordingSessionForm"]["goal"] = str(
                        session_form.get("goal") or builder["recordingSessionForm"]["goal"]
                    )
                if "captureScreenshots" in session_form:
                    builder["recordingSessionForm"]["captureScreenshots"] = bool(session_form.get("captureScreenshots"))
            if isinstance(loaded_builder.get("drafts"), list):
                builder["drafts"] = [self._normalize_source_draft(draft) for draft in loaded_builder["drafts"][:12]]

        loaded_v1 = loaded.get("v1Simple", {})
        v1 = state["v1Simple"]
        if isinstance(loaded_v1, dict):
            form = loaded_v1.get("form", {})
            if isinstance(form, dict):
                if str(form.get("subjectType") or "") in {"Person", "Company"}:
                    v1["form"]["subjectType"] = str(form.get("subjectType"))
                v1["form"]["subjectName"] = str(form.get("subjectName") or "")
                v1["form"]["subjectDetails"] = str(form.get("subjectDetails") or "")
                v1["form"]["googlePages"] = max(1, min(int(form.get("googlePages") or 1), 3))
                v1["form"]["photoCheckRequired"] = bool(form.get("photoCheckRequired", False))

            v1["outputRoot"] = self._sanitize_v1_output_root(loaded_v1.get("outputRoot") or "")

            if isinstance(loaded_v1.get("blockedDomains"), list):
                v1["blockedDomains"] = self._safe_domain_list(loaded_v1["blockedDomains"])

            loaded_approved = loaded_v1.get("approvedDomains")
            if isinstance(loaded_approved, list):
                v1["approvedDomains"] = self._safe_domain_list(loaded_approved)
            elif isinstance(loaded_v1.get("allowedDomainHints"), list):
                # Backward compatibility with the first V1 draft key.
                v1["approvedDomains"] = self._safe_domain_list(loaded_v1["allowedDomainHints"])

            if isinstance(loaded_v1.get("jobs"), list):
                normalized_jobs = []
                for job in loaded_v1["jobs"][:25]:
                    if not isinstance(job, dict):
                        continue
                    normalized_job = self._normalize_v1_job(job, v1["outputRoot"])
                    if "ravender" in normalized_job["folderPath"].lower():
                        continue
                    normalized_jobs.append(normalized_job)
                v1["jobs"] = normalized_jobs

            migrated_jobs = []
            for job in v1["jobs"]:
                migrated = dict(job)
                if not migrated.get("approvedDomains"):
                    migrated["approvedDomains"] = list(v1["approvedDomains"])
                if not migrated.get("blockedDomains"):
                    migrated["blockedDomains"] = list(v1["blockedDomains"])
                migrated["approvedDomains"] = self._safe_domain_list(migrated["approvedDomains"], limit=40)
                migrated["blockedDomains"] = self._safe_domain_list(migrated["blockedDomains"], limit=40)
                migrated.setdefault("lastRunAt", "")
                migrated.setdefault("lastRunSummary", {})
                migrated_jobs.append(migrated)
            v1["jobs"] = migrated_jobs

        return state

    def _normalize_source_draft(self, draft: dict) -> dict:
        owner = sanitize_owner_label(draft.get("owner") or "Compliance Operations")
        normalized = {
            "id": str(draft.get("id") or f"source-{int(datetime.now(timezone.utc).timestamp() * 1000)}"),
            "name": str(draft.get("name") or "").strip(),
            "siteUrl": normalize_source_url(draft.get("siteUrl") or ""),
            "sourceType": str(draft.get("sourceType") or "Public website"),
            "description": str(draft.get("description") or "").strip(),
            "owner": owner,
            "status": str(draft.get("status") or "Draft"),
            "recordingStatus": str(draft.get("recordingStatus") or "Not started"),
            "testStatus": str(draft.get("testStatus") or "Not run"),
            "publishStatus": str(draft.get("publishStatus") or "Not published"),
            "createdAt": str(draft.get("createdAt") or utc_now()),
            "updatedAt": str(draft.get("updatedAt") or utc_now()),
            "lastLaunchedAt": str(draft.get("lastLaunchedAt") or ""),
            "lastRecordingEventAt": str(draft.get("lastRecordingEventAt") or ""),
            "recordingAgendaType": str(draft.get("recordingAgendaType") or "").strip(),
            "recordingGoal": str(draft.get("recordingGoal") or "").strip(),
            "captureScreenshots": bool(draft.get("captureScreenshots", False)),
            "steps": [],
        }

        raw_steps = draft.get("steps", [])
        if isinstance(raw_steps, list):
            for index, step in enumerate(raw_steps, start=1):
                if not isinstance(step, dict):
                    continue
                normalized["steps"].append(
                    {
                        "id": str(step.get("id") or f"{normalized['id']}-step-{index}"),
                        "sequence": int(step.get("sequence") or index),
                        "actionType": str(step.get("actionType") or "Open page"),
                        "pageName": str(step.get("pageName") or "").strip(),
                        "targetLabel": str(step.get("targetLabel") or "").strip(),
                        "selectorHint": str(step.get("selectorHint") or "").strip(),
                        "value": str(step.get("value") or "").strip(),
                        "notes": str(step.get("notes") or "").strip(),
                        "capturedAt": str(step.get("capturedAt") or utc_now()),
                    }
                )

        return normalized

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
                "name": "AMEX Compliance Evidence Desk",
                "version": "1.0.0",
                "tagline": "Focused daily web search intake for compliance evidence collection.",
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
                "form": blank_source_builder_form(),
                "recordingSessionForm": blank_recording_session_form(),
                "recordingForm": blank_recording_form(),
                "sourceTypes": ["Public website", "Login website", "Internal portal"],
                "agendaTypes": [
                    {
                        "id": "search",
                        "label": "Search workflow",
                        "description": "Use this when the admin is teaching the tool how to search by name, company, or other lookup inputs.",
                    },
                    {
                        "id": "task",
                        "label": "Perform a task",
                        "description": "Use this when the admin is teaching a multi-step workflow such as opening records or moving through a process.",
                    },
                    {
                        "id": "evidence",
                        "label": "Capture screenshots",
                        "description": "Use this when the main goal is evidence capture, page checkpoints, or screenshot-oriented review.",
                    },
                    {
                        "id": "extract",
                        "label": "Extract profile data",
                        "description": "Use this when the admin wants the tool to land on pages and pull structured result fields later.",
                    },
                ],
                "actionTypes": ["Open page", "Click", "Type text", "Select option", "Wait", "Open result", "Extract value", "Capture screenshot"],
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
                    "Source definitions are saved locally as drafts on this machine.",
                    "Record Steps now starts with an agenda so the admin can say what kind of workflow is being taught before recording begins.",
                    "Automatic browser instrumentation, input mapping, testing, and publishing still come in later slices.",
                ],
            },
            "v1Simple": {
                "workflowName": "Google Evidence Search V1",
                "outputRoot": self._sanitize_v1_output_root(str(self._default_v1_workspace_root())),
                "form": blank_v1_search_form(),
                "blockedDomains": [
                    "linkedin.com",
                    "facebook.com",
                    "instagram.com",
                    "x.com",
                    "twitter.com",
                    "tiktok.com",
                ],
                "approvedDomains": [
                    ".gov",
                    ".nic.in",
                    ".gov.uk",
                    ".gc.ca",
                    "sec.gov",
                    "fca.org.uk",
                    "rbi.org.in",
                    "bseindia.com",
                ],
                "jobs": [],
                "notes": [
                    "This version keeps one focused workflow only.",
                    "Each request gets a dedicated local folder with request metadata.",
                    "Execution automation for Google pages and evidence capture is added in the next step.",
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

    def _find_source_draft(self, draft_id: str) -> dict:
        for draft in self._state["sourceBuilder"]["drafts"]:
            if draft["id"] == draft_id:
                return draft
        raise KeyError(f"Source draft not found: {draft_id}")

    def _find_v1_job(self, job_id: str) -> dict:
        for job in self._state["v1Simple"]["jobs"]:
            if job["id"] == job_id:
                return job
        raise KeyError(f"Search request not found: {job_id}")

    def _resolve_job_file_path(self, job: dict, relative_path: str) -> Path:
        base = Path(job["folderPath"]).resolve()
        target = (base / str(relative_path or "").replace("\\", "/")).resolve()
        if not str(target).startswith(str(base)):
            raise ValueError("Invalid artifact path.")
        if not target.exists() or not target.is_file():
            raise ValueError("Artifact file not found.")
        return target

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

    def create_v1_search_request(
        self,
        *,
        subject_type: str,
        subject_name: str,
        subject_details: str,
        google_pages: int,
        photo_check_required: bool,
    ) -> dict:
        with self._lock:
            v1 = self._state["v1Simple"]
            cleaned_type = str(subject_type or "").strip()
            cleaned_name = str(subject_name or "").strip()
            cleaned_details = str(subject_details or "").strip()

            if cleaned_type not in {"Person", "Company"}:
                raise ValueError("Search type must be Person or Company.")
            if not cleaned_name:
                raise ValueError("Name to search is required.")

            pages = max(1, min(int(google_pages), 3))
            created_at = utc_now()
            stamp = int(datetime.now(timezone.utc).timestamp() * 1000)
            slug = slugify_folder_name(cleaned_name)[:56]
            folder_name = f"{slug}-{stamp}"

            workspace_root = Path(v1["outputRoot"])
            request_folder = workspace_root / folder_name
            pdf_folder = request_folder / "pdf"
            screenshots_folder = request_folder / "screenshots"
            notes_folder = request_folder / "notes"
            pdf_folder.mkdir(parents=True, exist_ok=True)
            screenshots_folder.mkdir(parents=True, exist_ok=True)
            notes_folder.mkdir(parents=True, exist_ok=True)

            request_payload = {
                "id": f"v1-{stamp}",
                "createdAt": created_at,
                "subjectType": cleaned_type,
                "subjectName": cleaned_name,
                "subjectDetails": cleaned_details,
                "googlePages": pages,
                "photoCheckRequired": bool(photo_check_required),
                "approvedDomains": list(v1["approvedDomains"]),
                "blockedDomains": list(v1["blockedDomains"]),
                "status": "Request created",
                "folderPath": str(request_folder.resolve()),
                "lastRunAt": "",
                "lastRunSummary": {},
            }

            request_file = request_folder / "request.json"
            summary_file = notes_folder / "summary.txt"
            request_file.write_text(json.dumps(request_payload, indent=2), encoding="utf-8")
            summary_file.write_text(
                (
                    "V1 request created.\n"
                    f"Name: {cleaned_name}\n"
                    f"Type: {cleaned_type}\n"
                    f"Google depth: first {pages} page(s)\n"
                    f"Photo check required: {'Yes' if photo_check_required else 'No'}\n"
                    "Execution automation is added in the next step.\n"
                ),
                encoding="utf-8",
            )

            request_payload["requestFilePath"] = str(request_file.resolve())
            request_payload["summaryFilePath"] = str(summary_file.resolve())

            v1["jobs"].insert(0, request_payload)
            v1["jobs"] = v1["jobs"][:25]
            v1["form"] = {
                "subjectType": cleaned_type,
                "subjectName": "",
                "subjectDetails": "",
                "googlePages": pages,
                "photoCheckRequired": bool(photo_check_required),
            }

            self._persist_state()
            return {
                "ok": True,
                "job": deepcopy(request_payload),
                "v1Simple": deepcopy(v1),
                "message": f"Request folder created for {cleaned_name}.",
            }

    def update_v1_domain_rule(self, *, list_type: str, action: str, domain: str) -> dict:
        with self._lock:
            v1 = self._state["v1Simple"]
            cleaned_type = str(list_type or "").strip().lower()
            cleaned_action = str(action or "").strip().lower()
            cleaned_domain = normalize_domain_entry(domain)

            if cleaned_type not in {"approved", "blocked"}:
                raise ValueError("List type must be approved or blocked.")
            if cleaned_action not in {"add", "remove"}:
                raise ValueError("Action must be add or remove.")

            key = "approvedDomains" if cleaned_type == "approved" else "blockedDomains"
            opposite_key = "blockedDomains" if cleaned_type == "approved" else "approvedDomains"
            target = list(v1[key])
            opposite = list(v1[opposite_key])

            if cleaned_action == "add":
                if cleaned_domain not in target:
                    target.append(cleaned_domain)
                if cleaned_domain in opposite:
                    opposite.remove(cleaned_domain)
                message = f"{cleaned_domain} added to {cleaned_type} domains."
            else:
                if cleaned_domain in target:
                    target.remove(cleaned_domain)
                    message = f"{cleaned_domain} removed from {cleaned_type} domains."
                else:
                    message = f"{cleaned_domain} was not present in {cleaned_type} domains."

            v1[key] = sorted(target)[:40]
            v1[opposite_key] = sorted(opposite)[:40]
            self._persist_state()
            return {
                "ok": True,
                "v1Simple": deepcopy(v1),
                "message": message,
            }

    def run_v1_search_request(self, job_id: str) -> dict:
        with self._lock:
            job = self._find_v1_job(job_id)
            job["status"] = "Running"
            self._persist_state()

        try:
            summary = run_v1_search_job(
                subject_name=job["subjectName"],
                subject_details=job["subjectDetails"],
                google_pages=job["googlePages"],
                photo_check_required=bool(job["photoCheckRequired"]),
                approved_domains=list(job.get("approvedDomains") or self._state["v1Simple"]["approvedDomains"]),
                blocked_domains=list(job.get("blockedDomains") or self._state["v1Simple"]["blockedDomains"]),
                request_folder=Path(job["folderPath"]),
            )
        except Exception as error:
            with self._lock:
                current_job = self._find_v1_job(job_id)
                current_job["status"] = "Execution failed"
                current_job["lastRunAt"] = utc_now()
                current_job["lastRunSummary"] = {"error": str(error)}
                self._persist_state()
                return {
                    "ok": False,
                    "job": deepcopy(current_job),
                    "v1Simple": deepcopy(self._state["v1Simple"]),
                    "message": f"Search execution failed: {error}",
                }

        with self._lock:
            current_job = self._find_v1_job(job_id)
            current_job["status"] = "Execution complete"
            current_job["lastRunAt"] = utc_now()
            current_job["lastRunSummary"] = summary
            self._persist_state()
            return {
                "ok": True,
                "job": deepcopy(current_job),
                "v1Simple": deepcopy(self._state["v1Simple"]),
                "message": f"Search execution completed for {current_job['subjectName']}.",
            }

    def list_v1_artifacts(self, job_id: str) -> dict:
        with self._lock:
            job = deepcopy(self._find_v1_job(job_id))

        folder = Path(job["folderPath"]).resolve()
        if not folder.exists():
            raise ValueError("Request folder does not exist on disk.")

        groups = [
            ("summary", "Summary", ["request.json", "notes/run_summary.json", "notes/run_summary.txt", "notes/summary.txt"]),
            ("pdf", "PDF Evidence", ["pdf/*.pdf"]),
            ("screenshots", "Screenshot Evidence", ["screenshots/*.png", "screenshots/*.jpg", "screenshots/*.jpeg", "screenshots/*.webp"]),
            ("debug", "Debug Search Files", ["search_raw/*.html"]),
        ]

        artifacts = {}
        for key, label, patterns in groups:
            items = []
            seen = set()
            for pattern in patterns:
                for path in folder.glob(pattern):
                    resolved = path.resolve()
                    if not resolved.is_file():
                        continue
                    rel = resolved.relative_to(folder).as_posix()
                    if rel in seen:
                        continue
                    seen.add(rel)
                    items.append(
                        {
                            "name": resolved.name,
                            "relativePath": rel,
                            "sizeBytes": int(resolved.stat().st_size),
                            "updatedAt": datetime.fromtimestamp(resolved.stat().st_mtime, timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                        }
                    )
            items.sort(key=lambda item: item["name"].lower())
            artifacts[key] = {
                "label": label,
                "count": len(items),
                "items": items,
            }

        return {
            "ok": True,
            "jobId": job["id"],
            "subjectName": job["subjectName"],
            "folderPath": str(folder),
            "artifacts": artifacts,
        }

    def read_v1_artifact(self, job_id: str, relative_path: str) -> dict:
        with self._lock:
            job = deepcopy(self._find_v1_job(job_id))
        target = self._resolve_job_file_path(job, relative_path)
        mime_type, _ = mimetypes.guess_type(str(target))
        return {
            "path": str(target),
            "name": target.name,
            "mimeType": mime_type or "application/octet-stream",
            "content": target.read_bytes(),
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
            cleaned_owner = sanitize_owner_label(owner)
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
                draft_record = self._normalize_source_draft(
                    {
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
                )
                builder["drafts"].insert(0, draft_record)
                builder["drafts"] = builder["drafts"][:12]

            builder["form"] = blank_source_builder_form(cleaned_owner)
            self._persist_state()
            return {
                "ok": True,
                "draft": deepcopy(draft_record),
                "sourceBuilder": deepcopy(builder),
                "message": f'Source draft saved for {cleaned_name}.',
            }

    def update_source_recording_action(
        self,
        draft_id: str,
        action: str,
        *,
        agenda_type: str = "",
        goal: str = "",
        capture_screenshots: bool = False,
    ) -> dict:
        with self._lock:
            builder = self._state["sourceBuilder"]
            draft = self._find_source_draft(draft_id)
            timestamp = utc_now()

            action_map = {
                "launch": ("Site launched", "Site opened for recording."),
                "start": ("Recording", "Recording started."),
                "pause": ("Paused", "Recording paused."),
                "stop": ("Stopped", "Recording stopped."),
                "save": ("Saved", "Recording saved as a draft sequence."),
            }
            if action not in action_map:
                raise ValueError("Unsupported recording action.")

            status, message = action_map[action]
            if action == "start":
                allowed_agendas = {entry["id"] for entry in builder["agendaTypes"]}
                cleaned_agenda = str(agenda_type or "").strip()
                if cleaned_agenda not in allowed_agendas:
                    raise ValueError("Choose a recording agenda before starting.")
                draft["recordingAgendaType"] = cleaned_agenda
                draft["recordingGoal"] = str(goal or "").strip()
                draft["captureScreenshots"] = bool(capture_screenshots)
                builder["recordingSessionForm"] = {
                    "agendaType": cleaned_agenda,
                    "goal": draft["recordingGoal"],
                    "captureScreenshots": draft["captureScreenshots"],
                }
            draft["recordingStatus"] = status
            draft["updatedAt"] = timestamp
            draft["lastRecordingEventAt"] = timestamp
            if action == "launch":
                draft["lastLaunchedAt"] = timestamp
            if action == "save":
                builder["recordingSessionForm"] = {
                    "agendaType": draft["recordingAgendaType"],
                    "goal": draft["recordingGoal"],
                    "captureScreenshots": draft["captureScreenshots"],
                }

            self._persist_state()
            return {
                "ok": True,
                "draft": deepcopy(draft),
                "sourceBuilder": deepcopy(builder),
                "message": f"{message} {draft['name']}.",
            }

    def add_source_recording_step(
        self,
        draft_id: str,
        *,
        action_type: str,
        page_name: str,
        target_label: str,
        selector_hint: str,
        value: str,
        notes: str,
    ) -> dict:
        with self._lock:
            builder = self._state["sourceBuilder"]
            draft = self._find_source_draft(draft_id)
            if not draft["recordingAgendaType"]:
                raise ValueError("Start a guided recording session before adding steps.")
            cleaned_action_type = str(action_type or "").strip()
            if cleaned_action_type not in set(builder["actionTypes"]):
                raise ValueError("A valid action type is required.")

            cleaned_page_name = str(page_name or "").strip()
            cleaned_target_label = str(target_label or "").strip()
            cleaned_selector_hint = str(selector_hint or "").strip()
            cleaned_value = str(value or "").strip()
            cleaned_notes = str(notes or "").strip()
            if not cleaned_target_label and not cleaned_selector_hint and not cleaned_value and not cleaned_notes:
                raise ValueError("Add at least a target label, selector hint, value, or note.")

            timestamp = utc_now()
            next_sequence = len(draft["steps"]) + 1
            step_record = {
                "id": f"{draft['id']}-step-{next_sequence}",
                "sequence": next_sequence,
                "actionType": cleaned_action_type,
                "pageName": cleaned_page_name,
                "targetLabel": cleaned_target_label,
                "selectorHint": cleaned_selector_hint,
                "value": cleaned_value,
                "notes": cleaned_notes,
                "capturedAt": timestamp,
            }
            draft["steps"].append(step_record)
            draft["recordingStatus"] = "Recording" if draft["recordingStatus"] in {"Not started", "Saved"} else draft["recordingStatus"]
            draft["updatedAt"] = timestamp
            draft["lastRecordingEventAt"] = timestamp
            builder["recordingForm"] = blank_recording_form()

            self._persist_state()
            return {
                "ok": True,
                "draft": deepcopy(draft),
                "sourceBuilder": deepcopy(builder),
                "message": f"Recorded step {next_sequence} for {draft['name']}.",
            }
