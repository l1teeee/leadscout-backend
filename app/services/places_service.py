import asyncio
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
_TIMEOUT = 30.0

# Shared client — reuses TCP connections to places.googleapis.com so DNS is
# resolved once per process instead of once per call. Limited to 10 connections.
_http: httpx.AsyncClient | None = None


def _get_http() -> httpx.AsyncClient:
    global _http
    if _http is None:
        _http = httpx.AsyncClient(
            timeout=_TIMEOUT,
            limits=httpx.Limits(
                max_connections=10,
                max_keepalive_connections=5,
                keepalive_expiry=30.0,
            ),
        )
    return _http


def _places_key(
    query: str,
    location: str,
    radius_m: int,
    latitude: float | None = None,
    longitude: float | None = None,
) -> str:
    if latitude is not None and longitude is not None:
        zone_key = f"{latitude:.5f}:{longitude:.5f}"
    else:
        zone_key = "no-coordinates"
    raw = f"{query}:{location}:{radius_m}:{zone_key}".lower()
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
        raise ExternalServiceError("Google Places", "GOOGLE_PLACES_API_KEY is not configured.")

    key = _places_key(query, location, radius_m, latitude, longitude)
    cached = await cache.get(key)
    if cached is not None:
        logger.debug("Cache hit: places search %s in %s", query, location)
        return cached

    try:
        client = _get_http()
        if latitude is not None and longitude is not None:
            text_query = query
        else:
            text_query = f"{query} en {location}"

        body: dict = {
            "textQuery": text_query,
            "pageSize": 20,
            "languageCode": "es",
        }
        if latitude is not None and longitude is not None:
            import math
            delta_lat = radius_m / 111_320
            delta_lng = radius_m / (111_320 * math.cos(math.radians(latitude)))
            body["rankPreference"] = "DISTANCE"
            body["locationRestriction"] = {
                "rectangle": {
                    "low": {
                        "latitude": latitude - delta_lat,
                        "longitude": longitude - delta_lng,
                    },
                    "high": {
                        "latitude": latitude + delta_lat,
                        "longitude": longitude + delta_lng,
                    },
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

        next_token = payload.get("nextPageToken")
        if next_token:
            try:
                await asyncio.sleep(2)
                page2_resp = await client.post(
                    _TEXTSEARCH_URL,
                    json={**body, "pageToken": next_token},
                    headers={
                        "Content-Type": "application/json",
                        "X-Goog-Api-Key": settings.GOOGLE_PLACES_API_KEY,
                        "X-Goog-FieldMask": _TEXTSEARCH_FIELD_MASK,
                    },
                )
                page2_resp.raise_for_status()
                page2_payload = page2_resp.json()
                page2_results = [_normalize_place(p) for p in page2_payload.get("places", [])]
                results += page2_results
                logger.debug("Google Places page 2 fetched: %d places", len(page2_results))

                page3_token = page2_payload.get("nextPageToken")
                if page3_token:
                    try:
                        await asyncio.sleep(2)
                        page3_resp = await client.post(
                            _TEXTSEARCH_URL,
                            json={**body, "pageToken": page3_token},
                            headers={
                                "Content-Type": "application/json",
                                "X-Goog-Api-Key": settings.GOOGLE_PLACES_API_KEY,
                                "X-Goog-FieldMask": _TEXTSEARCH_FIELD_MASK,
                            },
                        )
                        page3_resp.raise_for_status()
                        page3_payload = page3_resp.json()
                        page3_results = [_normalize_place(p) for p in page3_payload.get("places", [])]
                        results += page3_results
                        logger.debug("Google Places page 3 fetched: %d places", len(page3_results))
                    except Exception as exc:
                        logger.warning("Google Places page 3 fetch failed: %s", exc)
            except Exception as exc:
                logger.warning("Google Places page 2 fetch failed: %s", exc)

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
        client = _get_http()
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
