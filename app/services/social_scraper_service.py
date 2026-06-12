import asyncio
import html
import ipaddress
import json
import logging
import re
import socket
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

from app.cache import cache
from app.scraping import FetchResult, fetch  # noqa: F401

logger = logging.getLogger(__name__)

_TIMEOUT = 12.0
_MAX_HTML_BYTES = 500_000
_USER_AGENT = "ScoutIA/1.0 (+https://scoutia.dev)"
_SCRAPE_CACHE_TTL = 43_200  # 12 hours
_MAX_SUBPAGES = 4
_MAX_EMAILS = 5
_MAX_PHONES = 5

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
    "/nosotros",
    "/quienes-somos",
    "/quienes",
    "/equipo",
    "/info",
    "/empresa",
    "/company",
    "/team",
)

# Keywords used to discover contact/about internal links from HTML
_CONTACT_LINK_KEYWORDS = (
    "contacto",
    "contact",
    "about",
    "nosotros",
    "quienes",
    "equipo",
    "info",
    "redes",
    "social",
)

# Patterns to reject obviously-bad email matches
_EMAIL_NOISE = re.compile(
    r"example\.com|sentry\.io|wixpress\.com|\.png|\.jpg|\.gif|\.svg|noreply|no-reply",
    re.IGNORECASE,
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


def _extract_from_jsonld(html_text: str) -> tuple[list[str], list[str], list[str]]:
    """Return (social_urls, emails, phones) from JSON-LD structured data."""
    social_urls: list[str] = []
    emails: list[str] = []
    phones: list[str] = []

    for script_content in re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html_text,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        try:
            data = json.loads(script_content)
        except (json.JSONDecodeError, ValueError):
            continue

        items = data if isinstance(data, list) else [data] if isinstance(data, dict) else []

        for item in items:
            same_as = item.get("sameAs") or []
            if isinstance(same_as, str):
                same_as = [same_as]
            for u in same_as:
                if isinstance(u, str) and u.startswith("http"):
                    social_urls.append(u)

            # telephone / email at root level
            for tel in _iter_str_or_list(item.get("telephone")):
                phones.append(tel)
            for em in _iter_str_or_list(item.get("email")):
                emails.append(em)

            # contactPoint
            cp = item.get("contactPoint") or []
            if isinstance(cp, dict):
                cp = [cp]
            for point in cp:
                if not isinstance(point, dict):
                    continue
                for tel in _iter_str_or_list(point.get("telephone")):
                    phones.append(tel)
                for em in _iter_str_or_list(point.get("email")):
                    emails.append(em)

    return social_urls, emails, phones


def _iter_str_or_list(value: object):
    if isinstance(value, str) and value.strip():
        yield value.strip()
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, str) and item.strip():
                yield item.strip()


def _extract_from_meta(html_text: str) -> list[str]:
    urls: list[str] = []

    for m in re.finditer(
        r'<meta[^>]+property=["\']og:see_also["\'][^>]+content=["\']([^"\']+)["\']',
        html_text,
        flags=re.IGNORECASE,
    ):
        urls.append(m.group(1))

    for m in re.finditer(
        r'<link[^>]+rel=["\']me["\'][^>]+href=["\']([^"\']+)["\']',
        html_text,
        flags=re.IGNORECASE,
    ):
        urls.append(m.group(1))

    return urls


def _extract_emails(html_text: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()

    # mailto: links
    for m in re.finditer(r'mailto:([^\s"\'<>?&]+)', html_text, flags=re.IGNORECASE):
        addr = m.group(1).lower().strip().rstrip(".,;)")
        if addr and addr not in seen and not _EMAIL_NOISE.search(addr):
            seen.add(addr)
            found.append(addr)

    # conservative email regex (not inside a URL path)
    for m in re.finditer(
        r'(?<![/@\w])([a-z0-9._%+\-]{1,64}@[a-z0-9.\-]{1,255}\.[a-z]{2,})',
        html_text,
        flags=re.IGNORECASE,
    ):
        addr = m.group(1).lower().strip()
        if addr and addr not in seen and not _EMAIL_NOISE.search(addr):
            seen.add(addr)
            found.append(addr)

    return found[:_MAX_EMAILS]


def _extract_phones(html_text: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()

    # tel: links
    for m in re.finditer(r'tel:([\+0-9\s\-\(\)]{6,20})', html_text, flags=re.IGNORECASE):
        number = re.sub(r'\s+', '', m.group(1)).strip()
        if number and number not in seen:
            seen.add(number)
            found.append(number)

    # wa.me / api.whatsapp.com links
    for m in re.finditer(
        r'(?:wa\.me/|api\.whatsapp\.com/send[^"\']*phone=)([\+0-9]{7,15})',
        html_text,
        flags=re.IGNORECASE,
    ):
        number = m.group(1).strip()
        if number and number not in seen:
            seen.add(number)
            found.append(number)

    return found[:_MAX_PHONES]


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


def _merge_emails(base: list[str], new: list[str]) -> list[str]:
    seen = set(base)
    result = list(base)
    for e in new:
        if e not in seen:
            seen.add(e)
            result.append(e)
    return result[:_MAX_EMAILS]


def _merge_phones(base: list[str], new: list[str]) -> list[str]:
    seen = set(base)
    result = list(base)
    for p in new:
        if p not in seen:
            seen.add(p)
            result.append(p)
    return result[:_MAX_PHONES]


def _extract_all_from_page(html_text: str, page_url: str) -> tuple[list[str], list[str], list[str]]:
    """Return (candidate_social_urls, emails, phones) from a single page."""
    candidate_urls: list[str] = []
    candidate_urls.extend(_extract_urls(html_text, page_url))
    jsonld_social, jsonld_emails, jsonld_phones = _extract_from_jsonld(html_text)
    candidate_urls.extend(jsonld_social)
    candidate_urls.extend(_extract_from_meta(html_text))

    emails = _merge_emails(_extract_emails(html_text), jsonld_emails)
    phones = _merge_phones(_extract_phones(html_text), jsonld_phones)
    return candidate_urls, emails, phones


def _discover_contact_links(html_text: str, base_url: str) -> list[str]:
    """Return same-origin hrefs whose path contains a contact/about keyword."""
    all_hrefs = re.findall(r"""href\s*=\s*["']([^"'#?]+)["']""", html_text, flags=re.IGNORECASE)
    results: list[str] = []
    seen: set[str] = set()
    for href in all_hrefs:
        full = urljoin(base_url, html.unescape(href.strip()))
        path = urlparse(full).path.lower()
        if any(kw in path for kw in _CONTACT_LINK_KEYWORDS) and _same_origin(base_url, full):
            norm = full.rstrip("/")
            if norm not in seen:
                seen.add(norm)
                results.append(full)
    return results


async def _scrape_website(url: str) -> dict:
    """Fetch homepage + up to _MAX_SUBPAGES contact/about sub-pages."""
    result = await fetch(url)
    if result is None:
        return {
            "status": "failed",
            "reason": "Website fetch failed or was blocked.",
            "profiles": [],
            "contacts": {"emails": [], "phones": []},
        }

    final_url = result.final_url
    html_text = result.html

    candidate_urls, all_emails, all_phones = _extract_all_from_page(html_text, final_url)
    profiles = _dedupe_profiles(candidate_urls)

    # Discover contact-looking links from homepage HTML
    discovered_links = _discover_contact_links(html_text, final_url)

    # Build the subpage queue: discovered links first, then guessed paths
    parsed_base = urlparse(final_url)
    base = f"{parsed_base.scheme}://{parsed_base.netloc}"
    guessed_urls = [base + path for path in _CONTACT_PATHS]

    subpage_queue: list[str] = []
    seen_sub: set[str] = set()
    for link in [*discovered_links, *guessed_urls]:
        norm = link.rstrip("/")
        if norm not in seen_sub and norm != final_url.rstrip("/"):
            seen_sub.add(norm)
            subpage_queue.append(link)

    pages_fetched = 0
    for sub_url in subpage_queue:
        if pages_fetched >= _MAX_SUBPAGES:
            break
        sub_result = await fetch(sub_url)
        if sub_result is None:
            continue
        pages_fetched += 1

        sub_candidates, sub_emails, sub_phones = _extract_all_from_page(sub_result.html, sub_result.final_url)
        all_emails = _merge_emails(all_emails, sub_emails)
        all_phones = _merge_phones(all_phones, sub_phones)

        if not profiles:
            sub_profiles = _dedupe_profiles(sub_candidates)
            if sub_profiles:
                profiles = sub_profiles
                logger.debug(
                    "Social links found on sub-page %s: %d profiles",
                    sub_url,
                    len(sub_profiles),
                )

    contacts = {"emails": all_emails, "phones": all_phones}
    found = bool(profiles or all_emails or all_phones)
    return {
        "status": "found" if found else "none",
        "reason": (
            "Social links and/or contacts found in website content."
            if found
            else "No social links or contacts found after deep scrape."
        ),
        "profiles": profiles,
        "contacts": contacts,
    }


async def detect_social_profiles(website: str | None) -> dict:
    if not website:
        return {
            "status": "not_checked",
            "reason": "No website URL was available to scrape.",
            "profiles": [],
            "contacts": {"emails": [], "phones": []},
        }

    url = _with_scheme(website)
    platform = _platform_for_url(url)
    if platform:
        return {
            "status": "found",
            "reason": "Website URL is a social profile.",
            "profiles": [{"platform": platform, "url": _clean_social_url(url)}],
            "contacts": {"emails": [], "phones": []},
        }

    if not await _is_safe_url(url):
        return {
            "status": "skipped",
            "reason": "Website URL is not safe to fetch.",
            "profiles": [],
            "contacts": {"emails": [], "phones": []},
        }

    cache_key = f"social-scrape:{url}"
    cached = await cache.get(cache_key)
    if cached is not None:
        logger.debug("Social scrape cache hit for %s", url)
        return cached

    result = await _scrape_website(url)
    await cache.set(cache_key, result, ttl=_SCRAPE_CACHE_TTL)
    return result
