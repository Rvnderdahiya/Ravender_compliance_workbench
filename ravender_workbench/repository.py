from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import RLock


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


@dataclass
class WorkbenchRepository:
    engine: object

    def __post_init__(self) -> None:
        self._lock = RLock()
        self._state = self._build_seed_state()

    def _build_seed_state(self) -> dict:
        return {
            "product": {
                "name": "Ravender Workbench",
                "version": "0.1.0",
                "tagline": "Certified search packs for analysts who should only have to learn the UI.",
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
        ready_cases = sum(1 for case in cases if case["status"] in {"Ready to run", "Ready for analyst review"})
        published_packs = sum(1 for pack in packs if pack["status"] == "Published")
        certified_sources = sum(1 for source in sources if source["approvalState"] == "Certified")
        return [
            {"label": "Cases ready", "value": str(ready_cases)},
            {"label": "Published packs", "value": str(published_packs)},
            {"label": "Certified sources", "value": str(certified_sources)},
            {"label": "Audit coverage", "value": "100%"},
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
            return {"ok": True, "case": deepcopy(case), "message": result.get("message", "Source resumed.")}
