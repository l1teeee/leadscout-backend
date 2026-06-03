import hashlib
import logging

import httpx

from app.cache import TTL_PLACES, cache
from app.config import settings

logger = logging.getLogger(__name__)

_TEXTSEARCH_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"
_DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"
_DETAILS_FIELDS = (
    "name,formatted_address,formatted_phone_number,website,"
    "rating,user_ratings_total,geometry,business_status"
)
_TIMEOUT = 15.0


def _places_key(query: str, location: str, radius_m: int) -> str:
    raw = f"{query}:{location}:{radius_m}".lower()
    return f"places:{hashlib.md5(raw.encode()).hexdigest()}"


def _details_key(place_id: str) -> str:
    return f"place_details:{place_id}"


async def search_places(query: str, location: str, radius_m: int) -> list[dict]:
    if not settings.google_places_configured:
        return []

    key = _places_key(query, location, radius_m)
    cached = await cache.get(key)
    if cached is not None:
        logger.debug("Cache hit: places search %s in %s", query, location)
        return cached

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(_TEXTSEARCH_URL, params={
                "query": f"{query} in {location}",
                "radius": radius_m,
                "key": settings.GOOGLE_PLACES_API_KEY,
            })
            resp.raise_for_status()
            results = resp.json().get("results", [])
            if results:
                await cache.set(key, results, ttl=TTL_PLACES)
            return results
    except httpx.TimeoutException:
        logger.warning("Google Places timeout: query=%s", query)
        return []
    except httpx.HTTPError as exc:
        logger.error("Google Places HTTP error: %s", exc)
        return []


async def get_place_details(place_id: str) -> dict:
    if not settings.google_places_configured:
        return {}

    key = _details_key(place_id)
    cached = await cache.get(key)
    if cached is not None:
        logger.debug("Cache hit: place details %s", place_id)
        return cached

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(_DETAILS_URL, params={
                "place_id": place_id,
                "fields": _DETAILS_FIELDS,
                "key": settings.GOOGLE_PLACES_API_KEY,
            })
            resp.raise_for_status()
            result = resp.json().get("result", {})
            if result:
                await cache.set(key, result, ttl=TTL_PLACES)
            return result
    except httpx.TimeoutException:
        logger.warning("Google Places details timeout: place_id=%s", place_id)
        return {}
    except httpx.HTTPError as exc:
        logger.error("Google Places details error: %s", exc)
        return {}
