from __future__ import annotations

import os
from copy import deepcopy
from datetime import datetime, timezone


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


class MockAutomationEngine:
    name = "mock-certified-demo"

    def run_pack(self, case_record: dict, pack_record: dict) -> dict:
        subject = case_record["subject"]
        case_id = case_record["id"]
        high_risk = case_record["riskLevel"].lower() == "high"

        tasks = [
            {
                "sourceId": "public_adverse_media",
                "label": "Public Web Adverse Media",
                "status": "Complete",
                "hits": 2,
                "evidenceCount": 2,
                "lastRun": utc_now(),
                "actionLabel": "View evidence",
                "mode": "Direct replay",
            },
            {
                "sourceId": "griffin_profile",
                "label": "Griffin Customer Lookup",
                "status": "Complete",
                "hits": 1,
                "evidenceCount": 1,
                "lastRun": utc_now(),
                "actionLabel": "View evidence",
                "mode": "Browser-backed",
            },
            {
                "sourceId": "cadence_activity",
                "label": "Cadence Activity Lookup",
                "status": "Needs assist" if high_risk else "Complete",
                "hits": 0 if high_risk else 1,
                "evidenceCount": 0 if high_risk else 1,
                "lastRun": utc_now(),
                "actionLabel": "Resume source" if high_risk else "View evidence",
                "mode": "Browser-backed",
            },
        ]

        evidence = [
            {
                "id": f"{case_id}-media-1",
                "sourceId": "public_adverse_media",
                "title": "Regional business press mention",
                "summary": f"{subject} appears in a public article discussing a vendor dispute. Context requires analyst review before classification.",
                "capturedAt": utc_now(),
                "confidence": "Medium",
                "fields": {
                    "Search term": subject,
                    "Article date": "2026-03-29",
                    "Jurisdiction": case_record["country"],
                    "Disposition hint": "Context only, not yet adverse",
                },
            },
            {
                "id": f"{case_id}-media-2",
                "sourceId": "public_adverse_media",
                "title": "Open-web people search result",
                "summary": f"Open-web search surfaced a potential name match for {subject}. Date-of-birth alignment is still pending.",
                "capturedAt": utc_now(),
                "confidence": "Low",
                "fields": {
                    "Search term": subject,
                    "Match type": "Name-only",
                    "Escalation rule": "Analyst confirmation required",
                    "Channel": "Approved public search",
                },
            },
            {
                "id": f"{case_id}-griffin-1",
                "sourceId": "griffin_profile",
                "title": "Griffin customer profile",
                "summary": f"Griffin returned a single profile aligned to {subject}. Customer status is active and profile metadata is consistent with case inputs.",
                "capturedAt": utc_now(),
                "confidence": "High",
                "fields": {
                    "Customer ID": "GRF-110298",
                    "Line of business": case_record["lineOfBusiness"],
                    "Country": case_record["country"],
                    "Profile state": "Active",
                },
            },
        ]

        if not high_risk:
            evidence.append(
                {
                    "id": f"{case_id}-cadence-1",
                    "sourceId": "cadence_activity",
                    "title": "Cadence recent activity",
                    "summary": "Cadence history loaded successfully. Recent activity does not show unusual servicing notes in the last 30 days.",
                    "capturedAt": utc_now(),
                    "confidence": "High",
                    "fields": {
                        "Last review date": "2026-04-05",
                        "Last activity": "Routine account servicing",
                        "Escalation": "No immediate escalation from source",
                        "Workflow tier": "Browser-backed",
                    },
                }
            )

        summary = (
            "Potential open-web name matches detected. Internal profile match confirmed. "
            "Cadence requires assisted continuation before final disposition."
            if high_risk
            else "All certified sources completed. Internal profile match confirmed and no urgent servicing notes found."
        )

        return {
            "engine": self.name,
            "runMode": "mock",
            "summary": summary,
            "recommendedDecision": "Escalate" if high_risk else "No Match",
            "tasks": tasks,
            "evidence": evidence,
            "auditEvent": {
                "time": utc_now(),
                "actor": "Analyst demo run",
                "message": f"Executed pack {pack_record['name']} for case {case_id} using mock-certified-demo engine.",
            },
        }

    def resume_source(self, case_record: dict, source_id: str) -> dict:
        subject = case_record["subject"]
        case_id = case_record["id"]
        if source_id != "cadence_activity":
            return {
                "engine": self.name,
                "sourceId": source_id,
                "message": "Source resume is not required for this source in the pilot.",
                "taskUpdate": None,
                "evidence": [],
            }

        return {
            "engine": self.name,
            "sourceId": source_id,
            "message": "Cadence session resumed after analyst-assisted login.",
            "taskUpdate": {
                "sourceId": "cadence_activity",
                "label": "Cadence Activity Lookup",
                "status": "Complete",
                "hits": 1,
                "evidenceCount": 1,
                "lastRun": utc_now(),
                "actionLabel": "View evidence",
                "mode": "Browser-backed",
            },
            "evidence": [
                {
                    "id": f"{case_id}-cadence-resume-1",
                    "sourceId": "cadence_activity",
                    "title": "Cadence assisted continuation",
                    "summary": f"Cadence lookup completed after analyst re-authentication. No active escalations were found for {subject}.",
                    "capturedAt": utc_now(),
                    "confidence": "High",
                    "fields": {
                        "Resume reason": "Session timeout",
                        "Completion path": "Analyst-assisted browser session",
                        "Notes found": "No active escalations",
                        "Next step": "Proceed with disposition review",
                    },
                }
            ],
        }


class WorkflowServiceAdapter:
    def __init__(self, base_url: str, auth_token: str | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.auth_token = auth_token
        self.name = "workflow-service-placeholder"

    def run_pack(self, case_record: dict, pack_record: dict) -> dict:
        return {
            "engine": self.name,
            "runMode": "placeholder",
            "summary": (
                "Live workflow adapter is configured but not yet wired to execute certified Search Packs. "
                "Use mock mode for pilot demos until workflow mapping is implemented."
            ),
            "recommendedDecision": "Needs Review",
            "tasks": deepcopy(case_record.get("tasks", [])),
            "evidence": [],
            "auditEvent": {
                "time": utc_now(),
                "actor": "System",
                "message": f"Live workflow adapter placeholder invoked for {pack_record['name']} at {self.base_url}.",
            },
        }

    def resume_source(self, case_record: dict, source_id: str) -> dict:
        return {
            "engine": self.name,
            "sourceId": source_id,
            "message": "Source resume will be implemented when live session routing is connected.",
            "taskUpdate": None,
            "evidence": [],
        }


def build_engine():
    base_url = os.environ.get("RAVENDER_ENGINE_BASE_URL", "").strip()
    auth_token = os.environ.get("RAVENDER_ENGINE_AUTH_TOKEN", "").strip() or None
    if base_url:
        return WorkflowServiceAdapter(base_url=base_url, auth_token=auth_token)
    return MockAutomationEngine()
