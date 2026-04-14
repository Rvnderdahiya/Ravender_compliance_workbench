from __future__ import annotations

from dataclasses import dataclass
from html import unescape
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qs, quote_plus, urlsplit
from urllib.request import Request, urlopen


SEARCH_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

GOOGLE_BASE = "https://www.google.com/search"
MAX_BYTES = 2_500_000


@dataclass
class ParsedResult:
    url: str
    title: str
    source_page: int
    rank: int
    domain: str
    approved: bool
    blocked: bool


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def normalize_for_match(value: str) -> str:
    lowered = normalize_space(value).lower()
    lowered = re.sub(r"[^a-z0-9]+", " ", lowered)
    return normalize_space(lowered)


def parse_detail_terms(value: str) -> list[str]:
    terms: list[str] = []
    seen = set()
    for raw in re.split(r"[,;\n]+", value or ""):
        cleaned = normalize_space(raw)
        if len(cleaned) < 2:
            continue
        lowered = cleaned.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        terms.append(cleaned)
    return terms[:10]


def strip_html(html: str) -> str:
    cleaned = re.sub(r"(?is)<(script|style|noscript).*?>.*?</\1>", " ", html)
    cleaned = re.sub(r"(?is)<[^>]+>", " ", cleaned)
    return normalize_space(unescape(cleaned))


def build_result_digest_html(
    *,
    query: str,
    deduped: list[ParsedResult],
    approved_candidates: list[ParsedResult],
    blocked_skips: list[ParsedResult],
    not_approved_skips: list[ParsedResult],
    evaluated: list[dict],
) -> str:
    result_rows = []
    for result in deduped[:40]:
        if result.blocked:
            status = "Blocked"
        elif result.approved:
            status = "Approved"
        else:
            status = "Not approved"
        result_rows.append(
            "<tr>"
            f"<td>{result.source_page}</td>"
            f"<td>{result.rank}</td>"
            f"<td>{status}</td>"
            f"<td>{result.domain}</td>"
            f"<td><a href=\"{result.url}\">{result.title}</a></td>"
            "</tr>"
        )

    evaluated_rows = []
    for item in evaluated:
        artifact = item.get("artifact") or {}
        evaluated_rows.append(
            "<tr>"
            f"<td>{item.get('matchStrength', '')}</td>"
            f"<td>{'Yes' if item.get('photoPresent') else 'No'}</td>"
            f"<td>{'Yes' if artifact.get('pdfCaptured') else 'No'}</td>"
            f"<td>{'Yes' if artifact.get('screenshotCaptured') else 'No'}</td>"
            f"<td>{(item.get('pageError') or '-')[:180]}</td>"
            f"<td><a href=\"{item.get('url','')}\">{item.get('domain','')}</a></td>"
            "</tr>"
        )

    result_rows_html = "".join(result_rows) if result_rows else "<tr><td colspan='5'>No results captured.</td></tr>"
    evaluated_rows_html = "".join(evaluated_rows) if evaluated_rows else "<tr><td colspan='6'>No approved candidates evaluated.</td></tr>"

    return (
        "<!doctype html><html><head><meta charset='utf-8' />"
        "<style>"
        "body{font-family:Arial,sans-serif;padding:18px;color:#123;}"
        "h1,h2{margin:0 0 10px;} .meta{margin:0 0 16px;color:#456;}"
        "table{width:100%;border-collapse:collapse;margin:10px 0 18px;}"
        "th,td{border:1px solid #d0d7de;padding:6px 8px;font-size:12px;vertical-align:top;}"
        "th{background:#f4f8fc;text-align:left;} a{color:#0f4b7a;text-decoration:none;}"
        "</style></head><body>"
        f"<h1>Compliance Search Result Digest</h1>"
        f"<p class='meta'><strong>Query:</strong> {query}</p>"
        "<p class='meta'>"
        f"<strong>Total results:</strong> {len(deduped)} | "
        f"<strong>Approved:</strong> {len(approved_candidates)} | "
        f"<strong>Blocked:</strong> {len(blocked_skips)} | "
        f"<strong>Not approved:</strong> {len(not_approved_skips)}"
        "</p>"
        "<h2>Search Results</h2>"
        "<table><thead><tr><th>Page</th><th>Rank</th><th>Status</th><th>Domain</th><th>Title</th></tr></thead>"
        f"<tbody>{result_rows_html}</tbody></table>"
        "<h2>Approved Candidate Evaluation</h2>"
        "<table><thead><tr><th>Match</th><th>Photo</th><th>PDF</th><th>Screenshot</th><th>Error</th><th>URL</th></tr></thead>"
        f"<tbody>{evaluated_rows_html}</tbody></table>"
        "</body></html>"
    )


def domain_matches_rule(domain: str, rule: str) -> bool:
    normalized_domain = (domain or "").lower().strip()
    normalized_rule = (rule or "").lower().strip()
    if not normalized_domain or not normalized_rule:
        return False
    if normalized_rule.startswith("."):
        return normalized_domain.endswith(normalized_rule)
    return normalized_domain == normalized_rule or normalized_domain.endswith(f".{normalized_rule}")


def is_blocked(domain: str, blocked_domains: Iterable[str]) -> bool:
    return any(domain_matches_rule(domain, rule) for rule in blocked_domains)


def is_approved(domain: str, approved_domains: Iterable[str]) -> bool:
    return any(domain_matches_rule(domain, rule) for rule in approved_domains)


def fetch_text(url: str, timeout: int = 20) -> str:
    request = Request(url, headers=SEARCH_HEADERS)
    with urlopen(request, timeout=timeout) as response:
        raw = response.read(MAX_BYTES)
        return raw.decode("utf-8", errors="replace")


def parse_google_result_links(html: str, page_number: int, approved_domains: list[str], blocked_domains: list[str]) -> list[ParsedResult]:
    pattern = re.compile(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL)
    results: list[ParsedResult] = []
    seen_urls: set[str] = set()
    rank = 0

    for match in pattern.finditer(html):
        href = unescape(match.group(1)).strip()
        target = ""
        if href.startswith("/url?"):
            query = parse_qs(urlsplit(href).query)
            target = unescape((query.get("q") or [""])[0]).strip()
        elif href.startswith(("http://", "https://")):
            target = href

        if not target.startswith(("http://", "https://")):
            continue
        if target in seen_urls:
            continue
        seen_urls.add(target)

        parsed = urlsplit(target)
        domain = (parsed.hostname or "").lower()
        if not domain:
            continue
        if "google." in domain:
            continue

        title = strip_html(match.group(2))
        if not title:
            title = target

        rank += 1
        results.append(
            ParsedResult(
                url=target,
                title=title[:220],
                source_page=page_number,
                rank=rank,
                domain=domain,
                approved=is_approved(domain, approved_domains),
                blocked=is_blocked(domain, blocked_domains),
            )
        )

    return results


def parse_duckduckgo_result_links(html: str, page_number: int, approved_domains: list[str], blocked_domains: list[str]) -> list[ParsedResult]:
    pattern = re.compile(r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL)
    results: list[ParsedResult] = []
    seen_urls: set[str] = set()
    rank = 0

    for match in pattern.finditer(html):
        href = unescape(match.group(1)).strip()
        target = ""
        if href.startswith("//duckduckgo.com/l/?") or href.startswith("https://duckduckgo.com/l/?") or href.startswith("/l/?"):
            if href.startswith("//"):
                href = f"https:{href}"
            if href.startswith("/l/?"):
                href = f"https://duckduckgo.com{href}"
            query = parse_qs(urlsplit(href).query)
            target = unescape((query.get("uddg") or [""])[0]).strip()
        elif href.startswith(("http://", "https://")):
            target = href

        if not target.startswith(("http://", "https://")):
            continue
        if target in seen_urls:
            continue
        seen_urls.add(target)

        parsed = urlsplit(target)
        domain = (parsed.hostname or "").lower()
        if not domain:
            continue

        title = strip_html(match.group(2))
        if not title:
            title = target

        rank += 1
        results.append(
            ParsedResult(
                url=target,
                title=title[:220],
                source_page=page_number,
                rank=rank,
                domain=domain,
                approved=is_approved(domain, approved_domains),
                blocked=is_blocked(domain, blocked_domains),
            )
        )
    return results


def find_headless_browser() -> str | None:
    candidates = [
        shutil.which("msedge"),
        shutil.which("chrome"),
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ]
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        if path.exists():
            return str(path)
    return None


def run_headless_capture(browser: str, url: str, pdf_path: Path, screenshot_path: Path) -> tuple[bool, bool, str]:
    pdf_ok = False
    screenshot_ok = False
    note = "Browser capture unavailable."

    headless_modes = ["--headless=new", "--headless"]
    for mode in headless_modes:
        try:
            pdf_cmd = [
                browser,
                mode,
                "--disable-gpu",
                f"--print-to-pdf={str(pdf_path)}",
                url,
            ]
            subprocess.run(pdf_cmd, check=True, timeout=80, capture_output=True)
            pdf_ok = pdf_path.exists()
        except Exception:
            pdf_ok = False

        try:
            screenshot_cmd = [
                browser,
                mode,
                "--disable-gpu",
                f"--screenshot={str(screenshot_path)}",
                "--window-size=1366,2200",
                url,
            ]
            subprocess.run(screenshot_cmd, check=True, timeout=80, capture_output=True)
            screenshot_ok = screenshot_path.exists()
        except Exception:
            screenshot_ok = False

        if pdf_ok or screenshot_ok:
            note = f"Captured with {Path(browser).name} ({mode})."
            return pdf_ok, screenshot_ok, note

    return pdf_ok, screenshot_ok, note


def run_v1_search_job(
    *,
    subject_name: str,
    subject_details: str,
    google_pages: int,
    photo_check_required: bool,
    approved_domains: list[str],
    blocked_domains: list[str],
    request_folder: Path,
) -> dict:
    request_folder.mkdir(parents=True, exist_ok=True)
    raw_dir = request_folder / "search_raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    pdf_dir = request_folder / "pdf"
    screenshot_dir = request_folder / "screenshots"
    notes_dir = request_folder / "notes"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    notes_dir.mkdir(parents=True, exist_ok=True)

    query = normalize_space(f"{subject_name} {subject_details}")
    detail_terms = parse_detail_terms(subject_details)
    normalized_subject = normalize_for_match(subject_name)
    normalized_detail_terms = [(term, normalize_for_match(term)) for term in detail_terms]

    all_results: list[ParsedResult] = []
    warnings: list[str] = []
    browser = find_headless_browser()
    capture_notes: list[str] = []
    digest_pdf_captured = 0
    digest_screenshot_captured = 0

    for page in range(1, google_pages + 1):
        start = (page - 1) * 10
        url = f"{GOOGLE_BASE}?q={quote_plus(query)}&num=10&hl=en&start={start}"
        try:
            html = fetch_text(url)
            (raw_dir / f"google_page_{page}.html").write_text(html, encoding="utf-8")
            parsed = parse_google_result_links(html, page, approved_domains, blocked_domains)
            all_results.extend(parsed)
        except Exception as error:
            warnings.append(f"Google page {page} could not be processed: {error}")

    if not all_results:
        warnings.append("Google results were empty or restricted. Used fallback HTML search endpoint.")
        for page in range(1, google_pages + 1):
            offset = (page - 1) * 30
            fallback_url = f"https://duckduckgo.com/html/?q={quote_plus(query)}&s={offset}"
            try:
                html = fetch_text(fallback_url)
                (raw_dir / f"fallback_page_{page}.html").write_text(html, encoding="utf-8")
                parsed = parse_duckduckgo_result_links(html, page, approved_domains, blocked_domains)
                all_results.extend(parsed)
            except Exception as error:
                warnings.append(f"Fallback page {page} could not be processed: {error}")

    # De-duplicate while preserving rank order.
    seen_urls: set[str] = set()
    deduped: list[ParsedResult] = []
    for result in all_results:
        if result.url in seen_urls:
            continue
        seen_urls.add(result.url)
        deduped.append(result)

    approved_candidates = [item for item in deduped if item.approved and not item.blocked]
    blocked_skips = [item for item in deduped if item.blocked]
    not_approved_skips = [item for item in deduped if not item.approved and not item.blocked]

    evaluated = []

    for index, candidate in enumerate(approved_candidates[:10], start=1):
        page_text = ""
        html = ""
        page_error = ""
        try:
            html = fetch_text(candidate.url, timeout=25)
            (raw_dir / f"candidate_{index:02d}.html").write_text(html, encoding="utf-8")
            page_text = strip_html(html).lower()
        except Exception as error:
            page_error = str(error)

        normalized_blob = normalize_for_match(f"{page_text} {candidate.title} {candidate.url}")
        name_match = normalized_subject in normalized_blob if normalized_subject else False
        matched_detail_terms = [term for term, normalized in normalized_detail_terms if normalized and normalized in normalized_blob]
        has_photo = "<img" in html.lower() if html else False

        if name_match and (matched_detail_terms or not detail_terms):
            match_strength = "Strong"
        elif name_match:
            match_strength = "Possible"
        else:
            match_strength = "Weak"

        artifact = {
            "pdfPath": "",
            "screenshotPath": "",
            "pdfCaptured": False,
            "screenshotCaptured": False,
            "captureNote": "",
        }

        should_capture = index <= 5 or match_strength in {"Strong", "Possible"}
        if should_capture and browser:
            pdf_path = pdf_dir / f"{index:02d}_{candidate.domain}.pdf"
            screenshot_path = screenshot_dir / f"{index:02d}_{candidate.domain}.png"
            pdf_ok, screenshot_ok, note = run_headless_capture(browser, candidate.url, pdf_path, screenshot_path)
            artifact = {
                "pdfPath": str(pdf_path.resolve()) if pdf_ok else "",
                "screenshotPath": str(screenshot_path.resolve()) if screenshot_ok else "",
                "pdfCaptured": pdf_ok,
                "screenshotCaptured": screenshot_ok,
                "captureNote": note,
            }
            if note:
                capture_notes.append(note)
        elif should_capture and not browser:
            artifact["captureNote"] = "No headless browser found. Capture manually."

        evaluated.append(
            {
                "url": candidate.url,
                "domain": candidate.domain,
                "title": candidate.title,
                "sourcePage": candidate.source_page,
                "sourceRank": candidate.rank,
                "matchStrength": match_strength,
                "nameMatch": name_match,
                "matchedDetails": matched_detail_terms,
                "photoPresent": has_photo,
                "pageError": page_error,
                "photoCheckRequired": photo_check_required,
                "artifact": artifact,
            }
        )

    strong_matches = [item for item in evaluated if item["matchStrength"] == "Strong"]
    possible_matches = [item for item in evaluated if item["matchStrength"] == "Possible"]
    pdf_captured = sum(1 for item in evaluated if item["artifact"].get("pdfCaptured"))
    screenshots_captured = sum(1 for item in evaluated if item["artifact"].get("screenshotCaptured"))

    digest_html = build_result_digest_html(
        query=query,
        deduped=deduped,
        approved_candidates=approved_candidates,
        blocked_skips=blocked_skips,
        not_approved_skips=not_approved_skips,
        evaluated=evaluated,
    )
    digest_html_path = notes_dir / "result_digest.html"
    digest_html_path.write_text(digest_html, encoding="utf-8")
    if browser:
        digest_pdf_path = pdf_dir / "result_digest.pdf"
        digest_screenshot_path = screenshot_dir / "result_digest.png"
        digest_pdf_ok, digest_screenshot_ok, digest_note = run_headless_capture(
            browser,
            digest_html_path.resolve().as_uri(),
            digest_pdf_path,
            digest_screenshot_path,
        )
        if digest_pdf_ok:
            digest_pdf_captured = 1
        if digest_screenshot_ok:
            digest_screenshot_captured = 1
        if digest_note:
            capture_notes.append(digest_note)

    used_fallback = any("fallback" in note.lower() for note in warnings)
    summary = {
        "query": query,
        "searchPath": "Google + fallback" if used_fallback else "Google",
        "googlePagesRequested": google_pages,
        "searchPagePdfCaptured": 0,
        "searchPageScreenshotsCaptured": 0,
        "digestPdfCaptured": digest_pdf_captured,
        "digestScreenshotCaptured": digest_screenshot_captured,
        "googleResultsFound": len(deduped),
        "approvedCandidates": len(approved_candidates),
        "blockedSkipped": len(blocked_skips),
        "notApprovedSkipped": len(not_approved_skips),
        "evaluatedCandidates": len(evaluated),
        "strongMatches": len(strong_matches),
        "possibleMatches": len(possible_matches),
        "pdfCaptured": pdf_captured,
        "screenshotsCaptured": screenshots_captured,
        "warnings": warnings,
        "captureNotes": sorted(set(capture_notes)),
        "results": evaluated,
    }

    (notes_dir / "run_summary.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )
    (notes_dir / "run_summary.txt").write_text(
        (
            f"Query: {query}\n"
            f"Search path: {'Google + fallback' if used_fallback else 'Google'}\n"
            f"Google pages requested: {google_pages}\n"
            "Search pages PDF captured: 0\n"
            "Search pages screenshots captured: 0\n"
            f"Digest PDF captured: {digest_pdf_captured}\n"
            f"Digest screenshot captured: {digest_screenshot_captured}\n"
            f"Total results seen: {len(deduped)}\n"
            f"Approved candidates: {len(approved_candidates)}\n"
            f"Blocked skipped: {len(blocked_skips)}\n"
            f"Not approved skipped: {len(not_approved_skips)}\n"
            f"Strong matches: {len(strong_matches)}\n"
            f"Possible matches: {len(possible_matches)}\n"
            f"PDF captured: {pdf_captured}\n"
            f"Screenshots captured: {screenshots_captured}\n"
            f"Photo check required: {'Yes' if photo_check_required else 'No'}\n"
        ),
        encoding="utf-8",
    )

    return summary
