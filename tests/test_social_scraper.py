import asyncio

import pytest

from app.scraping.fetcher import FetchResult
from app.services import social_scraper_service as sss


def run(coro):
    return asyncio.run(coro)


_FIXTURE_HTML = """
<html><head>
<script type="application/ld+json">
{"@type":"LocalBusiness","name":"Cafe Test",
 "telephone":"+50321001000","email":"jsonld@cafetest.sv",
 "sameAs":["https://instagram.com/cafetest","https://facebook.com/cafetest"]}
</script>
</head><body>
<a href="https://instagram.com/cafetest">IG</a>
<a href="mailto:hola@cafetest.sv">Escribenos</a>
<a href="tel:+50322002000">Llamanos</a>
<a href="https://wa.me/50370003000">WhatsApp</a>
<a href="/contacto">Contacto</a>
</body></html>
"""


@pytest.fixture(autouse=True)
def _no_cache_no_ssrf(monkeypatch):
    async def _safe(_url):
        return True

    async def _get(_key):
        return None

    async def _set(_key, _value, ttl=0):
        return None

    monkeypatch.setattr(sss, "_is_safe_url", _safe)
    monkeypatch.setattr(sss.cache, "get", _get)
    monkeypatch.setattr(sss.cache, "set", _set)


def _mock_fetch_homepage_only(html: str):
    async def _fetch(url: str):
        if url.rstrip("/").endswith("cafetest.sv"):
            return FetchResult(html=html, final_url="https://cafetest.sv/", status=200, via="httpx")
        return None  # subpages fail/blocked

    return _fetch


class TestDetectSocialProfiles:
    def test_no_website_returns_not_checked(self):
        result = run(sss.detect_social_profiles(None))
        assert result["status"] == "not_checked"
        assert result["profiles"] == []
        assert result["contacts"] == {"emails": [], "phones": []}

    def test_url_is_already_social_profile(self):
        result = run(sss.detect_social_profiles("https://instagram.com/somebrand"))
        assert result["status"] == "found"
        assert result["profiles"][0]["platform"] == "instagram"

    def test_unsafe_url_skipped(self, monkeypatch):
        async def _unsafe(_url):
            return False

        monkeypatch.setattr(sss, "_is_safe_url", _unsafe)
        result = run(sss.detect_social_profiles("http://169.254.169.254"))
        assert result["status"] == "skipped"

    def test_deep_extraction_profiles_and_contacts(self, monkeypatch):
        monkeypatch.setattr(sss, "fetch", _mock_fetch_homepage_only(_FIXTURE_HTML))
        result = run(sss.detect_social_profiles("https://cafetest.sv"))

        assert result["status"] == "found"
        platforms = {p["platform"] for p in result["profiles"]}
        assert "instagram" in platforms
        assert "facebook" in platforms

        emails = result["contacts"]["emails"]
        phones = result["contacts"]["phones"]
        assert "hola@cafetest.sv" in emails
        assert "jsonld@cafetest.sv" in emails
        assert "+50322002000" in phones  # tel:
        assert "50370003000" in phones   # wa.me

    def test_fetch_failure_returns_failed(self, monkeypatch):
        async def _always_none(_url):
            return None

        monkeypatch.setattr(sss, "fetch", _always_none)
        result = run(sss.detect_social_profiles("https://blocked.example.sv"))
        assert result["status"] == "failed"
        assert result["contacts"] == {"emails": [], "phones": []}
