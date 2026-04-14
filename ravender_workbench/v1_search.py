from __future__ import annotations

import csv
from dataclasses import dataclass
from html import unescape
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qs, quote_plus, urlsplit
from urllib.request import Request, urlopen
from xml.etree import ElementTree


SEARCH_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

GOOGLE_BASE = "https://www.google.com/search"
MAX_BYTES = 2_500_000

BOT_CHALLENGE_MARKERS = [
    "unusual traffic from your computer network",
    "our systems have detected unusual traffic",
    "i'm not a robot",
    "sorry, but your computer",
    "complete the following challenge",
    "select all squares containing",
    "bots use duckduckgo too",
    "captcha",
    "verify you are human",
]


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


def parse_detail_tokens(value: str) -> list[str]:
    stop_words = {"and", "or", "the", "for", "with", "from", "into", "this", "that"}
    tokens = []
    seen = set()
    for token in normalize_for_match(value).split():
        if len(token) < 3:
            continue
        if token in stop_words:
            continue
        if token in seen:
            continue
        seen.add(token)
        tokens.append(token)
    return tokens[:16]


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


def parse_bing_rss_result_links(xml_text: str, page_number: int, approved_domains: list[str], blocked_domains: list[str]) -> list[ParsedResult]:
    results: list[ParsedResult] = []
    seen_urls: set[str] = set()
    rank = 0

    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
        return results

    for item in root.findall(".//item"):
        link_text = normalize_space(item.findtext("link", default=""))
        title_text = normalize_space(item.findtext("title", default=""))
        if not link_text.startswith(("http://", "https://")):
            continue
        if link_text in seen_urls:
            continue
        seen_urls.add(link_text)

        parsed = urlsplit(link_text)
        domain = (parsed.hostname or "").lower()
        if not domain:
            continue

        rank += 1
        results.append(
            ParsedResult(
                url=link_text,
                title=(title_text or link_text)[:220],
                source_page=page_number,
                rank=rank,
                domain=domain,
                approved=is_approved(domain, approved_domains),
                blocked=is_blocked(domain, blocked_domains),
            )
        )

    return results


def looks_like_bot_challenge(html: str) -> bool:
    lowered = (html or "").lower()
    return any(marker in lowered for marker in BOT_CHALLENGE_MARKERS)


def sanitize_token(value: str, fallback: str = "item", max_len: int = 42) -> str:
    token = normalize_for_match(value).replace(" ", "-").strip("-")
    if not token:
        token = fallback
    return token[:max_len]


def build_match_reason(
    *,
    name_match: bool,
    matched_detail_terms: list[str],
    matched_detail_tokens: list[str],
    detail_terms: list[str],
    detail_tokens: list[str],
    photo_check_required: bool,
    has_photo: bool,
) -> str:
    reasons: list[str] = []
    if name_match:
        reasons.append("name matched")
    else:
        reasons.append("name did not match")

    if detail_terms:
        if matched_detail_terms:
            reasons.append(f"matched details: {', '.join(matched_detail_terms)}")
        elif matched_detail_tokens:
            reasons.append(f"matched detail tokens: {', '.join(matched_detail_tokens)}")
        else:
            reasons.append("no detail terms matched")
    elif detail_tokens:
        if matched_detail_tokens:
            reasons.append(f"matched detail tokens: {', '.join(matched_detail_tokens)}")
        else:
            reasons.append("no detail tokens matched")

    if photo_check_required:
        reasons.append("photo found" if has_photo else "photo not found")

    return "; ".join(reasons)


def write_pdf_index_files(
    *,
    notes_dir: Path,
    query: str,
    search_path: str,
    entries: list[dict],
) -> tuple[Path, Path]:
    txt_path = notes_dir / "pdf_index.txt"
    csv_path = notes_dir / "pdf_index.csv"

    lines = [
        "Compliance Evidence PDF Index",
        f"Query: {query}",
        f"Search path: {search_path}",
        f"PDF records: {len(entries)}",
        "",
    ]

    if not entries:
        lines.append("No successful match PDFs were captured in this run.")
    else:
        for index, entry in enumerate(entries, start=1):
            lines.extend(
                [
                    f"{index}. PDF: {entry['pdfFileName']}",
                    f"   URL: {entry['url']}",
                    f"   Title: {entry['title']}",
                    f"   Match reason: {entry['matchReason']}",
                    f"   Photo present: {'Yes' if entry['photoPresent'] else 'No'}",
                    f"   Screenshot: {entry['screenshotFileName'] or '-'}",
                    "",
                ]
            )
    txt_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "pdf_file",
                "screenshot_file",
                "url",
                "domain",
                "title",
                "match_strength",
                "match_reason",
                "photo_present",
                "source_page",
                "source_rank",
            ]
        )
        for entry in entries:
            writer.writerow(
                [
                    entry["pdfFileName"],
                    entry["screenshotFileName"],
                    entry["url"],
                    entry["domain"],
                    entry["title"],
                    entry["matchStrength"],
                    entry["matchReason"],
                    "yes" if entry["photoPresent"] else "no",
                    entry["sourcePage"],
                    entry["sourceRank"],
                ]
            )

    return txt_path, csv_path


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
    pdf_path = pdf_path.expanduser().resolve()
    screenshot_path = screenshot_path.expanduser().resolve()
    pdf_ok = False
    screenshot_ok = False
    note = "Browser capture unavailable."

    headless_modes = ["--headless=new", "--headless"]
    for mode in headless_modes:
        with tempfile.TemporaryDirectory(prefix="amex_capture_") as temp_profile:
            common_args = [
                browser,
                mode,
                "--disable-gpu",
                "--no-first-run",
                "--disable-extensions",
                "--disable-dev-shm-usage",
                f"--user-data-dir={temp_profile}",
            ]

            try:
                pdf_cmd = [
                    *common_args,
                    f"--print-to-pdf={str(pdf_path)}",
                    url,
                ]
                subprocess.run(pdf_cmd, check=True, timeout=35, capture_output=True)
                pdf_ok = pdf_path.exists()
            except Exception:
                pdf_ok = False

            try:
                screenshot_cmd = [
                    *common_args,
                    f"--screenshot={str(screenshot_path)}",
                    "--window-size=1366,2200",
                    url,
                ]
                subprocess.run(screenshot_cmd, check=True, timeout=35, capture_output=True)
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
    request_folder = request_folder.expanduser().resolve()
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
    detail_tokens = parse_detail_tokens(subject_details)
    normalized_subject = normalize_for_match(subject_name)
    normalized_detail_terms = [(term, normalize_for_match(term)) for term in detail_terms]

    all_results: list[ParsedResult] = []
    warnings: list[str] = []
    capture_notes: list[str] = []
    browser = find_headless_browser()

    google_had_challenge = False
    for page in range(1, google_pages + 1):
        start = (page - 1) * 10
        url = f"{GOOGLE_BASE}?q={quote_plus(query)}&num=10&hl=en&start={start}"
        try:
            html = fetch_text(url)
            (raw_dir / f"google_page_{page}.html").write_text(html, encoding="utf-8")
            if looks_like_bot_challenge(html):
                google_had_challenge = True
                warnings.append(f"Google page {page} returned an anti-bot challenge and was skipped.")
                continue
            parsed = parse_google_result_links(html, page, approved_domains, blocked_domains)
            all_results.extend(parsed)
        except Exception as error:
            warnings.append(f"Google page {page} could not be processed: {error}")

    used_bing_rss = False
    used_duck_fallback = False
    if not all_results:
        warnings.append("Google results were empty or restricted. Bing RSS fallback was used.")
        used_bing_rss = True
        for page in range(1, google_pages + 1):
            start = (page - 1) * 10 + 1
            bing_url = f"https://www.bing.com/search?q={quote_plus(query)}&count=10&first={start}&format=rss&setlang=en-US"
            try:
                xml_text = fetch_text(bing_url)
                (raw_dir / f"bing_page_{page}.xml").write_text(xml_text, encoding="utf-8")
                parsed = parse_bing_rss_result_links(xml_text, page, approved_domains, blocked_domains)
                all_results.extend(parsed)
            except Exception as error:
                warnings.append(f"Bing RSS page {page} could not be processed: {error}")

    if not all_results:
        warnings.append("Bing RSS fallback returned no parseable results. DuckDuckGo HTML fallback was used.")
        used_duck_fallback = True
        fallback_had_challenge = False
        for page in range(1, google_pages + 1):
            offset = (page - 1) * 30
            fallback_url = f"https://duckduckgo.com/html/?q={quote_plus(query)}&s={offset}"
            try:
                html = fetch_text(fallback_url)
                (raw_dir / f"fallback_page_{page}.html").write_text(html, encoding="utf-8")
                if looks_like_bot_challenge(html):
                    fallback_had_challenge = True
                    warnings.append(f"Fallback page {page} returned an anti-bot challenge and was skipped.")
                    continue
                parsed = parse_duckduckgo_result_links(html, page, approved_domains, blocked_domains)
                all_results.extend(parsed)
            except Exception as error:
                warnings.append(f"Fallback page {page} could not be processed: {error}")
        if not all_results and (google_had_challenge or fallback_had_challenge):
            warnings.append("Search engines returned anti-bot pages. Manual browser run is required for this query.")

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

    if approved_candidates and not browser:
        warnings.append("No headless browser was found. Successful matches cannot be captured as PDFs automatically.")

    evaluated: list[dict] = []
    pdf_index_entries: list[dict] = []
    saved_evidence: list[dict] = []
    evidence_sequence = 0
    capture_attempt_limit = 5

    for index, candidate in enumerate(approved_candidates[:15], start=1):
        html = ""
        page_error = ""
        page_text = ""
        try:
            html = fetch_text(candidate.url, timeout=25)
            (raw_dir / f"candidate_{index:02d}.html").write_text(html, encoding="utf-8")
            if looks_like_bot_challenge(html):
                page_error = "Candidate page returned anti-bot challenge."
            else:
                page_text = strip_html(html).lower()
        except Exception as error:
            page_error = str(error)

        normalized_blob = normalize_for_match(f"{page_text} {candidate.title} {candidate.url}")
        name_match = normalized_subject in normalized_blob if normalized_subject else False
        matched_detail_terms = [term for term, normalized in normalized_detail_terms if normalized and normalized in normalized_blob]
        matched_detail_tokens = [token for token in detail_tokens if token in normalized_blob]
        has_photo = "<img" in html.lower() if html else False

        detail_criteria_met = False
        if not detail_terms and not detail_tokens:
            detail_criteria_met = True
        elif matched_detail_terms:
            detail_criteria_met = True
        elif detail_tokens:
            required_token_hits = 2 if len(detail_tokens) >= 2 else 1
            detail_criteria_met = len(matched_detail_tokens) >= required_token_hits

        if name_match and detail_criteria_met:
            match_strength = "Strong"
        elif name_match:
            match_strength = "Possible"
        else:
            match_strength = "Weak"

        match_reason = build_match_reason(
            name_match=name_match,
            matched_detail_terms=matched_detail_terms,
            matched_detail_tokens=matched_detail_tokens,
            detail_terms=detail_terms,
            detail_tokens=detail_tokens,
            photo_check_required=photo_check_required,
            has_photo=has_photo,
        )

        search_successful = match_strength == "Strong" and not page_error
        if photo_check_required:
            search_successful = search_successful and has_photo

        artifact = {
            "pdfPath": "",
            "screenshotPath": "",
            "pdfCaptured": False,
            "screenshotCaptured": False,
            "captureNote": "",
            "captureSkippedReason": "",
        }

        if search_successful and browser:
            if evidence_sequence >= capture_attempt_limit:
                artifact["captureSkippedReason"] = f"Capture cap reached ({capture_attempt_limit} successful pages per run)."
            else:
                evidence_sequence += 1
                domain_part = sanitize_token(candidate.domain, fallback="domain")
                file_stem = f"{evidence_sequence:02d}_p{candidate.source_page}_r{candidate.rank}_{domain_part}"
                pdf_path = pdf_dir / f"{file_stem}.pdf"
                screenshot_path = screenshot_dir / f"{file_stem}.png"
                pdf_ok, screenshot_ok, note = run_headless_capture(browser, candidate.url, pdf_path, screenshot_path)
                artifact = {
                    "pdfPath": str(pdf_path.resolve()) if pdf_ok else "",
                    "screenshotPath": str(screenshot_path.resolve()) if screenshot_ok else "",
                    "pdfCaptured": pdf_ok,
                    "screenshotCaptured": screenshot_ok,
                    "captureNote": note,
                    "captureSkippedReason": "",
                }
                if note:
                    capture_notes.append(note)
                if not pdf_ok and not screenshot_ok:
                    artifact["captureSkippedReason"] = "Capture command ran but produced no file."

                if pdf_ok or screenshot_ok:
                    saved_evidence.append(
                        {
                            "url": candidate.url,
                            "domain": candidate.domain,
                            "title": candidate.title,
                            "sourcePage": candidate.source_page,
                            "sourceRank": candidate.rank,
                            "matchStrength": match_strength,
                            "matchReason": match_reason,
                            "photoPresent": has_photo,
                            "pdfCaptured": pdf_ok,
                            "screenshotCaptured": screenshot_ok,
                            "pdfFileName": pdf_path.name if pdf_ok else "",
                            "screenshotFileName": screenshot_path.name if screenshot_ok else "",
                        }
                    )
                    if pdf_ok:
                        pdf_index_entries.append(
                            {
                                "pdfFileName": pdf_path.name,
                                "screenshotFileName": screenshot_path.name if screenshot_ok else "",
                                "url": candidate.url,
                                "domain": candidate.domain,
                                "title": candidate.title,
                                "matchStrength": match_strength,
                                "matchReason": match_reason,
                                "photoPresent": has_photo,
                                "sourcePage": candidate.source_page,
                                "sourceRank": candidate.rank,
                            }
                        )
        elif search_successful and not browser:
            artifact["captureSkippedReason"] = "No browser available for automatic capture."
        else:
            if page_error:
                artifact["captureSkippedReason"] = page_error
            elif match_strength != "Strong":
                artifact["captureSkippedReason"] = "Skipped because the match was not strong."
            elif photo_check_required and not has_photo:
                artifact["captureSkippedReason"] = "Skipped because photo check is required and no photo was detected."

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
                "matchedDetailTokens": matched_detail_tokens,
                "photoPresent": has_photo,
                "photoCheckRequired": photo_check_required,
                "matchReason": match_reason,
                "searchSuccessful": search_successful,
                "pageError": page_error,
                "artifact": artifact,
            }
        )

    strong_matches = [item for item in evaluated if item["matchStrength"] == "Strong"]
    possible_matches = [item for item in evaluated if item["matchStrength"] == "Possible"]
    successful_matches = [item for item in evaluated if item["searchSuccessful"]]
    saved_pdf_count = sum(1 for item in saved_evidence if item["pdfCaptured"])
    saved_screenshot_count = sum(1 for item in saved_evidence if item["screenshotCaptured"])
    if len(successful_matches) > capture_attempt_limit:
        warnings.append(
            f"Only the first {capture_attempt_limit} successful pages were captured in this run to keep execution fast."
        )

    path_parts = ["Google"]
    if used_bing_rss:
        path_parts.append("Bing RSS")
    if used_duck_fallback:
        path_parts.append("DuckDuckGo fallback")
    search_path = " + ".join(path_parts)
    pdf_index_text_path, pdf_index_csv_path = write_pdf_index_files(
        notes_dir=notes_dir,
        query=query,
        search_path=search_path,
        entries=pdf_index_entries,
    )

    summary = {
        "query": query,
        "searchPath": search_path,
        "googlePagesRequested": google_pages,
        "googleResultsFound": len(deduped),
        "approvedCandidates": len(approved_candidates),
        "blockedSkipped": len(blocked_skips),
        "notApprovedSkipped": len(not_approved_skips),
        "evaluatedCandidates": len(evaluated),
        "strongMatches": len(strong_matches),
        "possibleMatches": len(possible_matches),
        "successfulMatches": len(successful_matches),
        "savedPdfCount": saved_pdf_count,
        "savedScreenshotCount": saved_screenshot_count,
        "photoCheckRequired": photo_check_required,
        "pdfIndexTextPath": str(pdf_index_text_path.resolve()),
        "pdfIndexCsvPath": str(pdf_index_csv_path.resolve()),
        "warnings": warnings,
        "captureNotes": sorted(set(capture_notes)),
        "savedEvidence": saved_evidence,
        "results": evaluated,
    }

    (notes_dir / "run_summary.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )
    (notes_dir / "run_summary.txt").write_text(
        (
            f"Query: {query}\n"
            f"Search path: {search_path}\n"
            f"Google pages requested: {google_pages}\n"
            f"Total results seen: {len(deduped)}\n"
            f"Approved candidates: {len(approved_candidates)}\n"
            f"Blocked skipped: {len(blocked_skips)}\n"
            f"Not approved skipped: {len(not_approved_skips)}\n"
            f"Strong matches: {len(strong_matches)}\n"
            f"Possible matches: {len(possible_matches)}\n"
            f"Successful matches: {len(successful_matches)}\n"
            f"Saved PDFs: {saved_pdf_count}\n"
            f"Saved screenshots: {saved_screenshot_count}\n"
            f"Photo check required: {'Yes' if photo_check_required else 'No'}\n"
            f"PDF index: {pdf_index_text_path.name}\n"
        ),
        encoding="utf-8",
    )

    return summary
