import asyncio
import html
import ipaddress
import re
import socket
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import httpx

_TIMEOUT = 8.0
_MAX_HTML_BYTES = 500_000
_USER_AGENT = "ScoutIA/1.0 (+https://scoutia.dev)"

_SOCIAL_DOMAINS: tuple[tuple[str, str], ...] = (
    ("instagram", "instagram.com"),
    ("facebook", "facebook.com"),
    ("facebook", "fb.com"),
    ("tiktok", "tiktok.com"),
    ("linkedin", "linkedin.com"),
    ("youtube", "youtube.com"),
    ("youtube", "youtu.be"),
    ("x", "x.com"),
    ("x", "twitter.com"),
    ("whatsapp", "wa.me"),
    ("whatsapp", "whatsapp.com"),
    ("linktree", "linktr.ee"),
)

_SKIP_PATH_PARTS = (
    "/share",
    "/sharer",
    "/intent",
    "/privacy",
    "/policy",
    "/terms",
    "/plugins/",
    "/dialog/",
)


def _with_scheme(url: str) -> str:
    value = url.strip()
    if not value:
        return value
    parsed = urlparse(value)
    if parsed.scheme:
        return value
    return f"https://{value}"


def _is_private_hostname(hostname: str) -> bool:
    host = hostname.strip().strip("[]").lower()
    if host in {"localhost", "0.0.0.0"} or host.endswith(".local"):
        return True

    try:
        ip = ipaddress.ip_address(host)
        return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
    except ValueError:
        return False


async def _host_resolves_to_private_ip(hostname: str) -> bool:
    try:
        infos = await asyncio.to_thread(socket.getaddrinfo, hostname, None)
    except socket.gaierror:
        return False

    for info in infos:
        address = info[4][0]
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            continue
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return True
    return False


async def _is_safe_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    if _is_private_hostname(parsed.hostname):
        return False
    return not await _host_resolves_to_private_ip(parsed.hostname)


def _platform_for_url(url: str) -> str | None:
    host = (urlparse(url).hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]

    for platform, domain in _SOCIAL_DOMAINS:
        if host == domain or host.endswith(f".{domain}"):
            return platform
    return None


def _clean_social_url(raw_url: str) -> str:
    parsed = urlparse(raw_url)
    query = urlencode(
        [
            (key, value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if not key.lower().startswith("utm_") and key.lower() not in {"fbclid", "gclid"}
        ],
        doseq=True,
    )
    return urlunparse((parsed.scheme, parsed.netloc.lower(), parsed.path.rstrip("/"), "", query, ""))


def _is_candidate_profile(url: str) -> bool:
    parsed = urlparse(url)
    path = parsed.path.lower()
    if any(part in path for part in _SKIP_PATH_PARTS):
        return False
    if parsed.fragment:
        return False
    return True


def _extract_urls(html_text: str, base_url: str) -> list[str]:
    hrefs = re.findall(r"""href\s*=\s*["']([^"']+)["']""", html_text, flags=re.IGNORECASE)
    plain_urls = re.findall(r"""https?://[^\s"'<>]+""", html_text, flags=re.IGNORECASE)
    return [urljoin(base_url, html.unescape(value.strip())) for value in [*hrefs, *plain_urls]]


def _dedupe_profiles(urls: list[str]) -> list[dict[str, str]]:
    seen_platforms: set[str] = set()
    seen_urls: set[str] = set()
    profiles: list[dict[str, str]] = []

    for url in urls:
        platform = _platform_for_url(url)
        if not platform or not _is_candidate_profile(url):
            continue

        clean_url = _clean_social_url(url)
        key = clean_url.lower()
        if key in seen_urls:
            continue

        seen_urls.add(key)
        if platform in seen_platforms and platform not in {"facebook", "youtube"}:
            continue

        seen_platforms.add(platform)
        profiles.append({"platform": platform, "url": clean_url})
        if len(profiles) >= 8:
            break

    return profiles


async def detect_social_profiles(website: str | None) -> dict:
    if not website:
        return {
            "status": "not_checked",
            "reason": "No website URL was available to scrape.",
            "profiles": [],
        }

    url = _with_scheme(website)
    platform = _platform_for_url(url)
    if platform:
        return {"status": "found", "reason": "Website URL is a social profile.", "profiles": [{"platform": platform, "url": _clean_social_url(url)}]}

    if not await _is_safe_url(url):
        return {"status": "skipped", "reason": "Website URL is not safe to fetch.", "profiles": []}

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
            response = await client.get(
                url,
                headers={
                    "User-Agent": _USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml",
                },
            )
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            if "html" not in content_type.lower():
                return {"status": "none", "reason": "Website response was not HTML.", "profiles": []}
            html_text = response.content[:_MAX_HTML_BYTES].decode(response.encoding or "utf-8", errors="ignore")
    except httpx.HTTPError as exc:
        return {"status": "failed", "reason": f"Website fetch failed: {exc.__class__.__name__}", "profiles": []}

    profiles = _dedupe_profiles(_extract_urls(html_text, str(response.url)))
    return {
        "status": "found" if profiles else "none",
        "reason": "Social links found in website HTML." if profiles else "No social links found in website HTML.",
        "profiles": profiles,
    }
