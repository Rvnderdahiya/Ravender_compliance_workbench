from __future__ import annotations

import gzip
import ipaddress
import re
import socket
import time
import zlib
from collections import deque
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Iterable
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen
from xml.etree import ElementTree


USER_AGENT = "AMEX-Compliance-Evidence-Desk/1.0"
MAX_FETCH_BYTES = 1_500_000
MAX_DISCOVERED_LINKS_PER_PAGE = 40
MAX_SITEMAPS = 2
MAX_SITEMAP_URLS = 60
DEFAULT_TIMEOUT = 15

EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PHONE_RE = re.compile(r"(?:\+\d{1,3}\s*)?(?:\(?\d{2,4}\)?[\s.-]*){2,5}\d{2,4}")
SPACE_RE = re.compile(r"\s+")
DATE_RE = re.compile(r"^(?:\d{4}\s*[-/]\s*\d{1,2}\s*[-/]\s*\d{1,2}|\d{1,2}\s*[-/]\s*\d{1,2}\s*[-/]\s*\d{2,4})$")
YEAR_RANGE_RE = re.compile(r"^\d{4}\s*[-/]\s*\d{4}$")


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def normalize_space(value: str) -> str:
    return SPACE_RE.sub(" ", value or "").strip()


def host_key(hostname: str | None) -> str:
    if not hostname:
        return ""
    hostname = hostname.lower().strip(".")
    return hostname[4:] if hostname.startswith("www.") else hostname


def is_same_public_site(candidate_host: str | None, root_host: str | None) -> bool:
    candidate = host_key(candidate_host)
    root = host_key(root_host)
    if not candidate or not root:
        return False
    return candidate == root or candidate.endswith(f".{root}")


def normalize_public_url(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        raise ValueError("A website URL is required.")
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", raw):
        raw = f"https://{raw}"

    parsed = urlsplit(raw)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Only http and https public websites are supported.")
    if not parsed.netloc:
        raise ValueError("A valid website host is required.")

    hostname = parsed.hostname or ""
    lowered = hostname.lower()
    if lowered in {"localhost"} or lowered.endswith(".local") or lowered.endswith(".internal"):
        raise ValueError("Only public website hosts are allowed.")

    path = parsed.path or "/"
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, parsed.query, ""))


def assert_public_target(url: str) -> None:
    parsed = urlsplit(url)
    hostname = parsed.hostname or ""

    try:
        address = ipaddress.ip_address(hostname)
        if not address.is_global:
            raise ValueError("Only public website hosts are allowed.")
        return
    except ValueError:
        pass

    try:
        infos = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        return

    for info in infos[:10]:
        resolved = info[4][0]
        try:
            address = ipaddress.ip_address(resolved)
        except ValueError:
            continue
        if not address.is_global:
            raise ValueError("The target resolves to a non-public network address.")


class HtmlInsightParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hidden_depth = 0
        self.in_title = False
        self.current_heading_tag: str | None = None
        self.current_heading_parts: list[str] = []
        self.current_link: dict | None = None
        self.title_parts: list[str] = []
        self.description = ""
        self.headings: list[dict] = []
        self.links: list[dict] = []
        self.text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        if tag in {"script", "style", "noscript", "svg"}:
            self.hidden_depth += 1
            return

        if tag == "title":
            self.in_title = True
            return

        if tag in {"h1", "h2", "h3"}:
            self.current_heading_tag = tag
            self.current_heading_parts = []
            return

        if tag == "a":
            href = attrs_dict.get("href")
            if href:
                self.current_link = {"href": href, "text_parts": []}
            return

        if tag == "meta":
            name = (attrs_dict.get("name") or attrs_dict.get("property") or "").lower()
            content = normalize_space(attrs_dict.get("content") or "")
            if name in {"description", "og:description", "twitter:description"} and content and not self.description:
                self.description = content

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self.hidden_depth > 0:
            self.hidden_depth -= 1
            return

        if tag == "title":
            self.in_title = False
            return

        if tag in {"h1", "h2", "h3"} and self.current_heading_tag == tag:
            text = normalize_space(" ".join(self.current_heading_parts))
            if text:
                self.headings.append({"level": tag, "text": text})
            self.current_heading_tag = None
            self.current_heading_parts = []
            return

        if tag == "a" and self.current_link:
            text = normalize_space(" ".join(self.current_link["text_parts"]))
            self.links.append(
                {
                    "href": self.current_link["href"],
                    "text": text,
                }
            )
            self.current_link = None

    def handle_data(self, data: str) -> None:
        if self.hidden_depth > 0:
            return
        text = normalize_space(data)
        if not text:
            return

        if self.in_title:
            self.title_parts.append(text)
        if self.current_heading_tag is not None:
            self.current_heading_parts.append(text)
        if self.current_link is not None:
            self.current_link["text_parts"].append(text)
        self.text_parts.append(text)


def decode_response(raw: bytes, content_type: str) -> str:
    match = re.search(r"charset=([^\s;]+)", content_type, re.IGNORECASE)
    charsets = [match.group(1)] if match else []
    charsets.extend(["utf-8", "latin-1"])
    for charset in charsets:
        if not charset:
            continue
        try:
            return raw.decode(charset, errors="replace")
        except LookupError:
            continue
    return raw.decode("utf-8", errors="replace")


def maybe_decompress(raw: bytes, content_encoding: str) -> bytes:
    encodings = [entry.strip().lower() for entry in (content_encoding or "").split(",") if entry.strip()]
    if not encodings:
        return raw

    data = raw
    for encoding in reversed(encodings):
        if encoding in {"gzip", "x-gzip"}:
            data = gzip.decompress(data)
            continue
        if encoding == "deflate":
            try:
                data = zlib.decompress(data)
            except zlib.error:
                data = zlib.decompress(data, -zlib.MAX_WBITS)
            continue
        if encoding in {"identity", "br"}:
            continue
    return data


def looks_like_low_quality_text(text: str) -> bool:
    sample = text[:2000]
    if not sample:
        return False

    control_count = sum(1 for char in sample if ord(char) < 32 and char not in "\n\r\t")
    replacement_count = sample.count("\ufffd")
    control_ratio = control_count / len(sample)
    replacement_ratio = replacement_count / len(sample)
    return control_ratio > 0.02 or replacement_ratio > 0.08


def looks_like_date_or_year_range(raw: str, groups: list[str]) -> bool:
    compact = normalize_space(raw)
    if DATE_RE.fullmatch(compact) or YEAR_RANGE_RE.fullmatch(compact):
        return True

    if len(groups) == 3:
        group_lengths = [len(group) for group in groups]
        if group_lengths[0] == 4 and group_lengths[1] <= 2 and group_lengths[2] <= 2:
            return True
        if group_lengths[2] == 4 and group_lengths[0] <= 2 and group_lengths[1] <= 2:
            return True

    if len(groups) == 4 and sum(1 for group in groups if len(group) == 4 and group.startswith(("19", "20"))) >= 1:
        if all(len(group) <= 4 for group in groups):
            return True

    return False


def fetch_url(url: str, timeout: int = DEFAULT_TIMEOUT) -> dict:
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,text/plain;q=0.8,*/*;q=0.7",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate",
        },
    )

    with urlopen(request, timeout=timeout) as response:
        final_url = response.geturl()
        content_type = response.headers.get("Content-Type", "application/octet-stream")
        content_encoding = response.headers.get("Content-Encoding", "")
        status_code = getattr(response, "status", 200)
        raw = response.read(MAX_FETCH_BYTES + 1)
        truncated = len(raw) > MAX_FETCH_BYTES
        if truncated:
            raw = raw[:MAX_FETCH_BYTES]
        raw = maybe_decompress(raw, content_encoding)
        text = decode_response(raw, content_type)
        if looks_like_low_quality_text(text):
            raise ValueError(f"Unusable text response returned by {final_url}")
        return {
            "url": url,
            "finalUrl": final_url,
            "statusCode": status_code,
            "contentType": content_type,
            "text": text,
            "truncated": truncated,
        }


def extract_contacts(text: str) -> tuple[list[str], list[str]]:
    emails = sorted({match.group(0).lower() for match in EMAIL_RE.finditer(text)})
    phones = []
    seen = set()
    for match in PHONE_RE.finditer(text):
        raw = normalize_space(match.group(0))
        digits = re.sub(r"\D", "", raw)
        if len(digits) < 8 or len(digits) > 15:
            continue
        groups = re.findall(r"\d+", raw)
        if len(groups) == 1 and not raw.startswith("+"):
            continue
        if looks_like_date_or_year_range(raw, groups):
            continue
        if len(groups) > 5 and not raw.startswith("+"):
            continue
        has_strong_phone_format = any(marker in raw for marker in "+-().")
        has_long_group = any(len(group) >= 4 for group in groups)
        if not has_strong_phone_format and not has_long_group:
            continue
        if not has_strong_phone_format and len(groups) >= 4 and not raw.startswith("+"):
            continue
        if digits in seen:
            continue
        seen.add(digits)
        phones.append(raw)
    return emails[:20], phones[:20]


def parse_query_terms(query: str) -> list[str]:
    raw_terms = re.split(r"[\n,;]+", query or "")
    terms = []
    seen = set()
    for term in raw_terms:
        cleaned = normalize_space(term)
        if not cleaned:
            continue
        lowered = cleaned.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        terms.append(cleaned)
    return terms[:10]


def build_snippets(text: str, query_terms: list[str], limit: int = 3) -> list[str]:
    source = normalize_space(text)
    if not source:
        return []

    snippets: list[str] = []
    seen = set()

    for term in query_terms:
        pattern = re.compile(re.escape(term), re.IGNORECASE)
        for match in pattern.finditer(source):
            start = max(match.start() - 90, 0)
            end = min(match.end() + 110, len(source))
            snippet = source[start:end].strip()
            if start > 0:
                snippet = f"...{snippet}"
            if end < len(source):
                snippet = f"{snippet}..."
            if snippet.lower() in seen:
                continue
            seen.add(snippet.lower())
            snippets.append(snippet)
            if len(snippets) >= limit:
                return snippets

    if not snippets and source:
        snippets.append(source[:220] + ("..." if len(source) > 220 else ""))
    return snippets


def normalize_candidate_url(base_url: str, href: str, root_host: str) -> str | None:
    candidate = (href or "").strip()
    if not candidate or candidate.startswith("#"):
        return None
    if candidate.startswith(("mailto:", "tel:", "javascript:")):
        return None

    try:
        absolute = normalize_public_url(urljoin(base_url, candidate))
    except ValueError:
        return None
    parsed = urlsplit(absolute)
    if not is_same_public_site(parsed.hostname, root_host):
        return None

    path = parsed.path.lower()
    if path.endswith((".jpg", ".jpeg", ".png", ".gif", ".svg", ".ico", ".zip", ".mp4", ".mp3", ".webp")):
        return None

    return absolute


def discover_sitemaps(start_url: str) -> list[str]:
    parsed = urlsplit(start_url)
    root = urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))
    robots_url = f"{root}/robots.txt"
    discovered: list[str] = []

    try:
        robots = fetch_url(robots_url, timeout=8)
        for line in robots["text"].splitlines():
            if line.lower().startswith("sitemap:"):
                sitemap_url = normalize_public_url(line.split(":", 1)[1].strip())
                if sitemap_url not in discovered:
                    discovered.append(sitemap_url)
    except Exception:
        pass

    default_sitemap = f"{root}/sitemap.xml"
    if default_sitemap not in discovered:
        discovered.append(default_sitemap)

    return discovered[:MAX_SITEMAPS]


def extract_sitemap_urls(sitemap_xml: str, root_host: str) -> list[str]:
    try:
        root = ElementTree.fromstring(sitemap_xml)
    except ElementTree.ParseError:
        return []

    discovered: list[str] = []
    for element in root.iter():
        if not element.tag.lower().endswith("loc"):
            continue
        text = normalize_space(element.text or "")
        if not text:
            continue
        try:
            candidate = normalize_public_url(text)
        except ValueError:
            continue
        if is_same_public_site(urlsplit(candidate).hostname, root_host):
            discovered.append(candidate)
        if len(discovered) >= MAX_SITEMAP_URLS:
            break
    return discovered


def analyze_page(fetch_result: dict, query_terms: list[str], root_host: str) -> dict:
    parser = HtmlInsightParser()
    parser.feed(fetch_result["text"])

    title = normalize_space(" ".join(parser.title_parts))
    text = normalize_space(" ".join(parser.text_parts))
    emails, phones = extract_contacts(text)

    matched_terms = [term for term in query_terms if term.lower() in text.lower() or term.lower() in title.lower()]
    match_count = 0
    for term in matched_terms:
        match_count += text.lower().count(term.lower())
        match_count += title.lower().count(term.lower())

    resolved_links = []
    for link in parser.links[:MAX_DISCOVERED_LINKS_PER_PAGE]:
        candidate = normalize_candidate_url(fetch_result["finalUrl"], link["href"], root_host)
        if candidate:
            resolved_links.append({"url": candidate, "text": link["text"]})

    headings = [entry["text"] for entry in parser.headings[:8]]

    return {
        "url": fetch_result["finalUrl"],
        "statusCode": fetch_result["statusCode"],
        "contentType": fetch_result["contentType"].split(";", 1)[0].strip().lower(),
        "title": title or fetch_result["finalUrl"],
        "description": parser.description,
        "headings": headings,
        "matchedTerms": matched_terms,
        "matchCount": match_count,
        "snippets": build_snippets(text, query_terms),
        "emails": emails,
        "phones": phones,
        "links": resolved_links[:10],
        "linkCount": len(resolved_links),
        "textPreview": text[:280] + ("..." if len(text) > 280 else ""),
        "truncated": fetch_result["truncated"],
    }


def investigate_public_website(url: str, query: str, max_pages: int) -> dict:
    start_url = normalize_public_url(url)
    assert_public_target(start_url)

    max_pages = max(1, min(int(max_pages), 15))
    query_terms = parse_query_terms(query)
    root_host = urlsplit(start_url).hostname or ""

    started_at = utc_now()
    started_perf = time.perf_counter()
    pages: list[dict] = []
    crawl_notes: list[dict] = []
    limitations: list[str] = []
    discovered_emails: set[str] = set()
    discovered_phones: set[str] = set()

    queue: deque[str] = deque([start_url])
    seen: set[str] = {start_url}

    for sitemap_url in discover_sitemaps(start_url):
        try:
            sitemap_fetch = fetch_url(sitemap_url, timeout=8)
            if "xml" not in sitemap_fetch["contentType"].lower():
                continue
            for candidate in extract_sitemap_urls(sitemap_fetch["text"], root_host):
                if candidate not in seen:
                    seen.add(candidate)
                    queue.append(candidate)
            crawl_notes.append({"type": "discovery", "message": f"Sitemap scanned: {sitemap_url}"})
        except Exception:
            continue

    while queue and len(pages) < max_pages:
        current_url = queue.popleft()
        try:
            fetch_result = fetch_url(current_url)
        except Exception as error:
            crawl_notes.append({"type": "error", "message": f"Could not fetch {current_url}: {error}"})
            continue

        content_type = fetch_result["contentType"].split(";", 1)[0].strip().lower()
        if content_type not in {"text/html", "application/xhtml+xml"}:
            crawl_notes.append({"type": "skip", "message": f"Skipped non-HTML content at {fetch_result['finalUrl']} ({content_type})."})
            continue

        page = analyze_page(fetch_result, query_terms, root_host)
        pages.append(page)
        discovered_emails.update(page["emails"])
        discovered_phones.update(page["phones"])

        crawl_notes.append(
            {
                "type": "page",
                "message": f"Crawled {page['url']} with {page['matchCount']} matches and {page['linkCount']} discovered links.",
            }
        )

        for link in page["links"]:
            candidate = link["url"]
            if candidate in seen:
                continue
            seen.add(candidate)
            queue.append(candidate)
            if len(seen) >= max_pages * 12:
                break

    if not pages:
        raise ValueError("No HTML pages could be analyzed from that public website.")

    duration_ms = int((time.perf_counter() - started_perf) * 1000)
    matched_pages = sum(1 for page in pages if page["matchCount"] > 0)

    if query_terms and matched_pages == 0:
        limitations.append("No exact query-term matches were found in the crawled HTML pages.")
    if len(pages) < max_pages:
        limitations.append("The crawl stopped when it ran out of same-site HTML pages to follow.")
    else:
        limitations.append("The crawl respected the page cap for safety and speed.")
    limitations.append("JavaScript-rendered content, CAPTCHA gates, and authenticated pages are not covered by this mode.")

    sorted_pages = sorted(pages, key=lambda page: (-page["matchCount"], page["url"]))
    top_page = sorted_pages[0]

    return {
        "id": f"public-{int(time.time() * 1000)}",
        "targetUrl": start_url,
        "finalUrl": top_page["url"],
        "domain": urlsplit(start_url).hostname or "",
        "startedAt": started_at,
        "completedAt": utc_now(),
        "durationMs": duration_ms,
        "query": query,
        "queryTerms": query_terms,
        "pagesCrawled": len(pages),
        "matchedPages": matched_pages,
        "emails": sorted(discovered_emails)[:20],
        "phones": sorted(discovered_phones)[:20],
        "pages": sorted_pages,
        "crawlNotes": crawl_notes[:20],
        "limitations": limitations,
        "summary": (
            f"Crawled {len(pages)} page(s) on {urlsplit(start_url).hostname or start_url} and found "
            f"{matched_pages} page(s) with matching content."
            if query_terms
            else f"Crawled {len(pages)} page(s) on {urlsplit(start_url).hostname or start_url} and built a site profile."
        ),
    }
