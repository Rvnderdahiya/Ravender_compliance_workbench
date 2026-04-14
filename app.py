from __future__ import annotations

import json
import mimetypes
import os
import re
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from ravender_workbench.engine import build_engine
from ravender_workbench.repository import WorkbenchRepository


ROOT_DIR = Path(__file__).resolve().parent
STATIC_DIR = ROOT_DIR / "static"
DATA_DIR = ROOT_DIR / "runtime_data"
REPO = WorkbenchRepository(engine=build_engine(), state_path=DATA_DIR / "workbench_state.json")


class WorkbenchHandler(BaseHTTPRequestHandler):
    server_version = "AMEXComplianceEvidenceDesk/1.0"

    def do_GET(self) -> None:
        path = urlparse(self.path).path

        if path == "/api/health":
            self._send_json({"ok": True, "service": "amex-compliance-evidence-desk"})
            return

        if path == "/api/bootstrap":
            self._send_json(REPO.get_bootstrap())
            return

        if path == "/" or path == "/index.html":
            self._serve_static("index.html")
            return

        if path.startswith("/static/"):
            self._serve_static(path.removeprefix("/static/"))
            return

        self._send_json({"error": f"Route not found: {path}"}, status=HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            payload = self._read_json_body()
        except ValueError as error:
            self._send_json({"error": str(error)}, status=HTTPStatus.BAD_REQUEST)
            return

        try:
            run_match = re.fullmatch(r"/api/cases/([^/]+)/run-pack", path)
            if run_match:
                case_id = run_match.group(1)
                pack_id = str(payload.get("packId", "")).strip()
                if not pack_id:
                    self._send_json({"error": "packId is required"}, status=HTTPStatus.BAD_REQUEST)
                    return
                self._send_json(REPO.run_pack(case_id, pack_id))
                return

            decision_match = re.fullmatch(r"/api/cases/([^/]+)/decision", path)
            if decision_match:
                case_id = decision_match.group(1)
                decision = str(payload.get("decision", "")).strip()
                notes = str(payload.get("notes", "")).strip()
                if not decision:
                    self._send_json({"error": "decision is required"}, status=HTTPStatus.BAD_REQUEST)
                    return
                self._send_json(REPO.save_decision(case_id, decision, notes))
                return

            resume_match = re.fullmatch(r"/api/cases/([^/]+)/resume-source", path)
            if resume_match:
                case_id = resume_match.group(1)
                source_id = str(payload.get("sourceId", "")).strip()
                if not source_id:
                    self._send_json({"error": "sourceId is required"}, status=HTTPStatus.BAD_REQUEST)
                    return
                self._send_json(REPO.resume_source(case_id, source_id))
                return

            if path == "/api/public-investigator/run":
                url = str(payload.get("url", "")).strip()
                query = str(payload.get("query", "")).strip()
                max_pages = int(payload.get("maxPages", 6))
                if not url:
                    self._send_json({"error": "url is required"}, status=HTTPStatus.BAD_REQUEST)
                    return
                self._send_json(REPO.run_public_investigation(url, query, max_pages))
                return

            if path == "/api/v1/search-requests":
                self._send_json(
                    REPO.create_v1_search_request(
                        subject_type=str(payload.get("subjectType", "")).strip(),
                        subject_name=str(payload.get("subjectName", "")).strip(),
                        subject_details=str(payload.get("subjectDetails", "")).strip(),
                        google_pages=int(payload.get("googlePages", 1)),
                        photo_check_required=bool(payload.get("photoCheckRequired", False)),
                    )
                )
                return

            if path == "/api/v1/domain-rules":
                self._send_json(
                    REPO.update_v1_domain_rule(
                        list_type=str(payload.get("listType", "")).strip(),
                        action=str(payload.get("action", "")).strip(),
                        domain=str(payload.get("domain", "")).strip(),
                    )
                )
                return

            run_v1_match = re.fullmatch(r"/api/v1/search-requests/([^/]+)/run", path)
            if run_v1_match:
                job_id = run_v1_match.group(1)
                self._send_json(REPO.run_v1_search_request(job_id))
                return

            if path == "/api/source-builder/drafts":
                self._send_json(
                    REPO.save_source_draft(
                        name=str(payload.get("name", "")).strip(),
                        site_url=str(payload.get("siteUrl", "")).strip(),
                        source_type=str(payload.get("sourceType", "")).strip(),
                        description=str(payload.get("description", "")).strip(),
                        owner=str(payload.get("owner", "")).strip(),
                    )
                )
                return

            recording_action_match = re.fullmatch(r"/api/source-builder/drafts/([^/]+)/recording-action", path)
            if recording_action_match:
                draft_id = recording_action_match.group(1)
                action = str(payload.get("action", "")).strip().lower()
                if not action:
                    self._send_json({"error": "action is required"}, status=HTTPStatus.BAD_REQUEST)
                    return
                self._send_json(
                    REPO.update_source_recording_action(
                        draft_id,
                        action,
                        agenda_type=str(payload.get("agendaType", "")).strip(),
                        goal=str(payload.get("goal", "")).strip(),
                        capture_screenshots=bool(payload.get("captureScreenshots", False)),
                    )
                )
                return

            recording_step_match = re.fullmatch(r"/api/source-builder/drafts/([^/]+)/steps", path)
            if recording_step_match:
                draft_id = recording_step_match.group(1)
                self._send_json(
                    REPO.add_source_recording_step(
                        draft_id,
                        action_type=str(payload.get("actionType", "")).strip(),
                        page_name=str(payload.get("pageName", "")).strip(),
                        target_label=str(payload.get("targetLabel", "")).strip(),
                        selector_hint=str(payload.get("selectorHint", "")).strip(),
                        value=str(payload.get("value", "")).strip(),
                        notes=str(payload.get("notes", "")).strip(),
                    )
                )
                return

            self._send_json({"error": f"Route not found: {path}"}, status=HTTPStatus.NOT_FOUND)
        except KeyError as error:
            self._send_json({"error": str(error)}, status=HTTPStatus.NOT_FOUND)
        except ValueError as error:
            self._send_json({"error": str(error)}, status=HTTPStatus.BAD_REQUEST)

    def log_message(self, format: str, *args: object) -> None:
        return

    def _read_json_body(self) -> dict:
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length <= 0:
            return {}
        raw = self.rfile.read(content_length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as error:
            raise ValueError("Invalid JSON body") from error
        if isinstance(data, dict):
            return data
        raise ValueError("JSON body must be an object")

    def _serve_static(self, relative_path: str) -> None:
        target = (STATIC_DIR / relative_path).resolve()
        if not str(target).startswith(str(STATIC_DIR.resolve())) or not target.exists() or not target.is_file():
            self._send_json({"error": "Static asset not found"}, status=HTTPStatus.NOT_FOUND)
            return

        mime_type, _ = mimetypes.guess_type(str(target))
        body = target.read_bytes()

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mime_type or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    port = int(os.environ.get("PORT", "8080"))
    server = ThreadingHTTPServer(("127.0.0.1", port), WorkbenchHandler)
    print(f"AMEX Compliance Evidence Desk listening on http://127.0.0.1:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
