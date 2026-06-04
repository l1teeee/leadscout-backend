import hashlib
import logging

import httpx

from app.cache import TTL_PLACES, cache
from app.config import settings
from app.exceptions import ExternalServiceError

logger = logging.getLogger(__name__)

_TEXTSEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
_DETAILS_URL = "https://places.googleapis.com/v1"
_TEXTSEARCH_FIELD_MASK = (
    "places.id,places.name,places.displayName,places.formattedAddress,"
    "places.location,places.nationalPhoneNumber,places.internationalPhoneNumber,"
    "places.websiteUri,places.rating,places.userRatingCount,places.businessStatus"
)
_DETAILS_FIELD_MASK = (
    "id,name,displayName,formattedAddress,location,nationalPhoneNumber,"
    "internationalPhoneNumber,websiteUri,rating,userRatingCount,businessStatus"
)
_TIMEOUT = 15.0


def _places_key(query: str, location: str, radius_m: int) -> str:
    raw = f"{query}:{location}:{radius_m}".lower()
    return f"places:{hashlib.md5(raw.encode()).hexdigest()}"


def _details_key(place_name: str) -> str:
    return f"place_details:{place_name}"


def _normalize_place(place: dict) -> dict:
    display_name = place.get("displayName") or {}
    location = place.get("location") or {}
    phone = place.get("nationalPhoneNumber") or place.get("internationalPhoneNumber")

    return {
        "place_id": place.get("id") or place.get("name", "").removeprefix("places/"),
        "place_resource_name": place.get("name"),
        "name": display_name.get("text") or "",
        "formatted_address": place.get("formattedAddress"),
        "formatted_phone_number": phone,
        "website": place.get("websiteUri"),
        "rating": place.get("rating"),
        "user_ratings_total": place.get("userRatingCount"),
        "business_status": place.get("businessStatus"),
        "geometry": {
            "location": {
                "lat": location.get("latitude"),
                "lng": location.get("longitude"),
            }
        },
    }


async def search_places(
    query: str,
    location: str,
    radius_m: int,
    latitude: float | None = None,
    longitude: float | None = None,
) -> list[dict]:
    if not settings.google_places_configured:
        if settings.MOCK_PLACES_ENABLED:
            return []
        raise ExternalServiceError("Google Places", "GOOGLE_PLACES_API_KEY is not configured.")

    key = _places_key(query, location, radius_m)
    cached = await cache.get(key)
    if cached is not None:
        logger.debug("Cache hit: places search %s in %s", query, location)
        return cached

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            body: dict = {
                "textQuery": f"{query} en {location}",
                "pageSize": 12,
                "languageCode": "es",
            }
            if latitude is not None and longitude is not None:
                body["locationBias"] = {
                    "circle": {
                        "center": {
                            "latitude": latitude,
                            "longitude": longitude,
                        },
                        "radius": radius_m,
                    }
                }

            resp = await client.post(
                _TEXTSEARCH_URL,
                json=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Goog-Api-Key": settings.GOOGLE_PLACES_API_KEY,
                    "X-Goog-FieldMask": _TEXTSEARCH_FIELD_MASK,
                },
            )
            resp.raise_for_status()
            payload = resp.json()
            results = [_normalize_place(place) for place in payload.get("places", [])]
            if results:
                await cache.set(key, results, ttl=TTL_PLACES)
            return results
    except httpx.TimeoutException:
        logger.warning("Google Places timeout: query=%s", query)
        return []
    except httpx.HTTPError as exc:
        detail = ""
        if getattr(exc, "response", None) is not None:
            detail = exc.response.text[:500]
        logger.error("Google Places HTTP error: %s %s", exc, detail)
        raise ExternalServiceError("Google Places", detail or str(exc))


async def get_place_details(place_name: str) -> dict:
    if not settings.google_places_configured:
        return {}

    key = _details_key(place_name)
    cached = await cache.get(key)
    if cached is not None:
        logger.debug("Cache hit: place details %s", place_name)
        return cached

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resource = place_name if place_name.startswith("places/") else f"places/{place_name}"
            resp = await client.get(
                f"{_DETAILS_URL}/{resource}",
                headers={
                    "X-Goog-Api-Key": settings.GOOGLE_PLACES_API_KEY,
                    "X-Goog-FieldMask": _DETAILS_FIELD_MASK,
                },
            )
            resp.raise_for_status()
            result = _normalize_place(resp.json())
            if result:
                await cache.set(key, result, ttl=TTL_PLACES)
            return result
    except httpx.TimeoutException:
        logger.warning("Google Places details timeout: place_name=%s", place_name)
        return {}
    except httpx.HTTPError as exc:
        logger.error("Google Places details error: %s", exc)
        return {}
