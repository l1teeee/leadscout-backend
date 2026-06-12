import asyncio
import html
import ipaddress
import json
import logging
import re
import socket
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import httpx

from app.cache import cache

logger = logging.getLogger(__name__)

_TIMEOUT = 12.0
_MAX_HTML_BYTES = 500_000
_USER_AGENT = "ScoutIA/1.0 (+https://scoutia.dev)"
_SCRAPE_CACHE_TTL = 43_200  # 12 hours

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
    "/login",
    "/signup",
    "/register",
)

# Sub-pages to probe when homepage yields no social links
_CONTACT_PATHS = (
    "/contacto",
    "/contact",
    "/contact-us",
    "/sobre-nosotros",
    "/about",
    "/about-us",
    "/acerca",
    "/acerca-de",
    "/redes-sociales",
    "/social",
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


def _same_origin(base_url: str, target_url: str) -> bool:
    try:
        base = urlparse(base_url)
        target = urlparse(target_url)
        return base.hostname == target.hostname
    except Exception:
        return False


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


def _extract_from_jsonld(html_text: str) -> list[str]:
    """Extract social URLs from JSON-LD structured data (sameAs property)."""
    urls: list[str] = []
    for script_content in re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html_text,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        try:
            data = json.loads(script_content)
        except (json.JSONDecodeError, ValueError):
            continue

        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            items = [data]
        else:
            continue

        for item in items:
            same_as = item.get("sameAs") or []
            if isinstance(same_as, str):
                same_as = [same_as]
            for u in same_as:
                if isinstance(u, str) and u.startswith("http"):
                    urls.append(u)

    return urls


def _extract_from_meta(html_text: str) -> list[str]:
    """Extract social links from meta tags (og:see_also, twitter:site, etc.)."""
    urls: list[str] = []

    # <meta property="og:see_also" content="https://facebook.com/..." />
    for m in re.finditer(
        r'<meta[^>]+property=["\']og:see_also["\'][^>]+content=["\']([^"\']+)["\']',
        html_text,
        flags=re.IGNORECASE,
    ):
        urls.append(m.group(1))

    # <meta name="twitter:site" content="@handle" /> — not a URL, skip

    # Facebook app-id meta can indicate a Facebook presence but isn't a profile URL

    # <link rel="me" href="https://..."> (IndieAuth / Mastodon)
    for m in re.finditer(
        r'<link[^>]+rel=["\']me["\'][^>]+href=["\']([^"\']+)["\']',
        html_text,
        flags=re.IGNORECASE,
    ):
        urls.append(m.group(1))

    return urls


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


async def _fetch_html(client: httpx.AsyncClient, url: str) -> str | None:
    try:
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
            return None
        return response.content[:_MAX_HTML_BYTES].decode(response.encoding or "utf-8", errors="ignore")
    except (httpx.HTTPError, Exception):
        return None


async def _scrape_website(url: str) -> dict:
    """Fetch homepage + up to 2 contact/about sub-pages, extract all social links."""
    async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
        try:
            response = await client.get(
                url,
                headers={
                    "User-Agent": _USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml",
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            return {"status": "failed", "reason": f"Website fetch failed: {exc.__class__.__name__}", "profiles": []}

        content_type = response.headers.get("content-type", "")
        if "html" not in content_type.lower():
            return {"status": "none", "reason": "Website response was not HTML.", "profiles": []}

        final_url = str(response.url)
        html_text = response.content[:_MAX_HTML_BYTES].decode(response.encoding or "utf-8", errors="ignore")

    # Collect candidate URLs from homepage: hrefs + JSON-LD + meta
    all_candidate_urls: list[str] = []
    all_candidate_urls.extend(_extract_urls(html_text, final_url))
    all_candidate_urls.extend(_extract_from_jsonld(html_text))
    all_candidate_urls.extend(_extract_from_meta(html_text))

    profiles = _dedupe_profiles(all_candidate_urls)

    # If homepage didn't yield social links, try contact/about sub-pages
    if not profiles:
        parsed_base = urlparse(final_url)
        base = f"{parsed_base.scheme}://{parsed_base.netloc}"

        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client2:
            pages_fetched = 0
            for path in _CONTACT_PATHS:
                if pages_fetched >= 2:
                    break
                sub_url = base + path
                sub_html = await _fetch_html(client2, sub_url)
                if sub_html is None:
                    continue
                pages_fetched += 1

                sub_candidates: list[str] = []
                sub_candidates.extend(_extract_urls(sub_html, sub_url))
                sub_candidates.extend(_extract_from_jsonld(sub_html))
                sub_candidates.extend(_extract_from_meta(sub_html))

                profiles = _dedupe_profiles(sub_candidates)
                if profiles:
                    logger.debug("Social links found on sub-page %s: %d profiles", path, len(profiles))
                    break

    return {
        "status": "found" if profiles else "none",
        "reason": "Social links found in website content." if profiles else "No social links found after deep scrape.",
        "profiles": profiles,
    }


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
        return {
            "status": "found",
            "reason": "Website URL is a social profile.",
            "profiles": [{"platform": platform, "url": _clean_social_url(url)}],
        }

    if not await _is_safe_url(url):
        return {"status": "skipped", "reason": "Website URL is not safe to fetch.", "profiles": []}

    cache_key = f"social-scrape:{url}"
    cached = await cache.get(cache_key)
    if cached is not None:
        logger.debug("Social scrape cache hit for %s", url)
        return cached

    result = await _scrape_website(url)
    await cache.set(cache_key, result, ttl=_SCRAPE_CACHE_TTL)
    return result
