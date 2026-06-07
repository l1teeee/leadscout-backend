import asyncio
import logging
import math

from app.exceptions import ExternalServiceError
from app.repositories import leads_repository, search_audit_repository
from app.schemas.explorer_schema import (
    ExplorerResultItem,
    ExplorerSearchRequest,
    ExplorerSearchResponse,
)
from app.services import ai_service, places_service, scoring_service

logger = logging.getLogger(__name__)

# Max concurrent place-detail fetches + DB writes. Keeps DNS/connection load low.
_PLACE_SEM = asyncio.Semaphore(10)

# Well-known chains and franchises to exclude from lead results.
_EXCLUDED_BRANDS: frozenset[str] = frozenset({
    # Fast food international
    "mcdonald", "mcdonalds", "burger king", "kfc", "kentucky fried", "pizza hut",
    "dominos", "domino's", "subway", "taco bell", "wendy's", "wendys", "popeyes",
    "little caesars", "papa john", "dunkin", "starbucks", "costa coffee",
    "church's chicken", "churchs chicken", "pollo campero",
    # Supermarkets / retail international
    "walmart", "super walmart", "costco", "sam's club", "sams club",
    "carrefour", "lidl", "aldi", "spar", "7-eleven", "seven eleven", "oxxo",
    # El Salvador / CA chains
    "raf", "la curacao", "almacenes siman", "siman", "multiplex",
    "super selectos", "super selecto", "despensa familiar", "despensa de don juan",
    "apopa", "metrocentro", "galerias escalon", "merliot", "multiplaza",
    "universal", "cemaco", "bazar el regalo", "tropigas",
    "banco agricola", "banco de america", "davivienda", "banco cuscatlan",
    "scotiabank", "bancosal", "credomatic", "promerica",
    "movistar", "tigo", "claro", "digicel",
    # Pharmacies / health chains
    "farmacia san nicolas", "farmacias san nicolas", "farmacia don juan",
    "farmacias don juan", "farmacias eba", "drogueria", "farmatodo",
    "farmacia económica", "farmacia economica",
    # Gas stations
    "texaco", "shell", "esso", "puma energy", "uno", "petrosun",
    # Hotels
    "marriott", "hilton", "sheraton", "hyatt", "holiday inn", "radisson",
    "best western", "ibis", "novotel", "intercontinental",
    # Banks / finance generic
    "citibank", "hsbc", "chase", "wells fargo", "santander", "bbva",
    # Delivery / tech
    "amazon", "uber", "rappi", "glovo", "dhl", "fedex", "ups",
})


def _is_excluded_brand(name: str) -> bool:
    lower = name.lower()
    return any(brand in lower for brand in _EXCLUDED_BRANDS)


def _priority_from_score(score: int) -> str:
    if score <= 20:
        return "alta"
    if score <= 40:
        return "media"
    return "baja"


def _to_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lng = math.radians(lng2 - lng1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(d_lng / 2) ** 2
    )
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _distance_from_search_center_km(
    place_latitude: object,
    place_longitude: object,
    request: ExplorerSearchRequest,
) -> float | None:
    if request.latitude is None or request.longitude is None:
        return None

    place_lat = _to_float(place_latitude)
    place_lng = _to_float(place_longitude)
    if place_lat is None or place_lng is None:
        return None

    return _haversine_km(request.latitude, request.longitude, place_lat, place_lng)


def _has_strict_search_zone(request: ExplorerSearchRequest) -> bool:
    return request.latitude is not None and request.longitude is not None


async def _log_search_audit(
    user_id: str,
    workspace_id: str,
    request: ExplorerSearchRequest,
    results_count: int,
    saved_new: int,
) -> None:
    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            lambda: search_audit_repository.log_search(
                user_id=user_id,
                workspace_id=workspace_id,
                query=request.query,
                location=request.location,
                category=request.category,
                radius_km=request.radius_km,
                latitude=request.latitude,
                longitude=request.longitude,
                results_count=results_count,
                saved_new=saved_new,
            ),
        )
    except Exception as exc:
        logger.warning("Search audit task failed: %s", exc)


async def _process_place(
    place: dict,
    workspace_id: str,
    request: ExplorerSearchRequest,
    loop: asyncio.AbstractEventLoop,
) -> tuple["ExplorerResultItem | None", int]:
    """Fetch details + write to DB for one place. Returns (item, saved_new)."""
    async with _PLACE_SEM:
        try:
            place_id = place.get("place_id", "")
            place_name = place.get("name", "")
            if _is_excluded_brand(place_name):
                logger.debug("Skipping known brand: %s", place_name)
                return None, 0

            place_resource_name = place.get("place_resource_name") or place_id
            details = await places_service.get_place_details(place_resource_name) if place_resource_name else {}
            place_data = {**place, **details, "category": request.category, "location": request.location}
            geo = place_data.get("geometry", {}).get("location", {})
            latitude = geo.get("lat")
            longitude = geo.get("lng")
            distance_km = _distance_from_search_center_km(latitude, longitude, request)

            if _has_strict_search_zone(request):
                if distance_km is None:
                    logger.debug("Skipping place without coordinates for strict zone: %s", place_name)
                    return None, 0
                if distance_km > request.radius_km:
                    logger.debug(
                        "Skipping place outside strict zone: %s %.2fkm > %.2fkm",
                        place_name,
                        distance_km,
                        request.radius_km,
                    )
                    return None, 0

            brand_check = await ai_service.classify_local_business_candidate(place_data)
            if not brand_check.get("eligible_local_business"):
                logger.info(
                    "Skipping non-local or recognized business: %s [%s] %s",
                    place_name,
                    brand_check.get("classification"),
                    brand_check.get("reason"),
                )
                return None, 0

            # Run sync Supabase calls in the thread pool to avoid blocking the event loop
            existing = None
            if place_id:
                existing = await loop.run_in_executor(None, leads_repository.find_by_place_id, place_id)

            has_website = bool(place_data.get("website"))
            has_phone = bool(place_data.get("formatted_phone_number"))
            has_rating = bool(place_data.get("rating"))

            score, issues = scoring_service.calculate_score(
                has_website=has_website,
                has_phone=has_phone,
                has_rating=has_rating,
                website_has_ssl=False,
                pagespeed_score=None,
                has_complete_google_business=has_rating and has_phone,
            )

            item = ExplorerResultItem(
                google_place_id=place_id,
                name=place_data.get("name", ""),
                category=request.category,
                address=place_data.get("formatted_address"),
                location=request.location,
                latitude=latitude,
                longitude=longitude,
                phone=place_data.get("formatted_phone_number"),
                website=place_data.get("website"),
                score=score,
                issues=issues,
                already_saved=existing is not None,
            )

            saved_new = 0
            if not existing and place_id:
                lead_data = {
                    "name": item.name,
                    "category": item.category,
                    "address": item.address,
                    "location": item.location,
                    "latitude": item.latitude,
                    "longitude": item.longitude,
                    "phone": item.phone,
                    "website": item.website,
                    "google_place_id": item.google_place_id,
                    "score": item.score,
                    "issues": item.issues,
                    "status": "nuevo",
                    "priority": _priority_from_score(item.score),
                    "source": "explorer",
                }
                await loop.run_in_executor(None, leads_repository.create_lead, workspace_id, lead_data)
                saved_new = 1

            return item, saved_new
        except ExternalServiceError:
            raise
        except Exception as exc:
            logger.warning("Skipping place due to error: %s", exc)
            return None, 0


async def search_and_save(workspace_id: str, user_id: str, request: ExplorerSearchRequest) -> ExplorerSearchResponse:
    logger.info(
        "Explorer search: query=%s location=%s radius=%.1fkm",
        request.query, request.location, request.radius_km,
    )
    await ai_service.validate_openai_ready()

    radius_m = int(request.radius_km * 1000)

    _GENERIC = {"local businesses", "negocios locales", "comercios", "general", "todas", "todos", "all", ""}
    base_query = request.query.strip()
    if base_query.lower() in _GENERIC:
        alt_queries = [
            "restaurantes cafeterías bares",
            "médicos clínicas dentistas",
            "hoteles hospedajes turismo",
            "tiendas farmacias supermercados",
            "salones gimnasios servicios profesionales",
        ]
    else:
        alt_queries = [
            base_query,
            f"negocios de {base_query}",
            f"servicios de {base_query}",
            f"empresas {base_query}",
            f"comercios {base_query}",
        ]

    search_tasks = [
        places_service.search_places(q, request.location, radius_m, request.latitude, request.longitude)
        for q in alt_queries
    ]
    all_results = await asyncio.gather(*search_tasks, return_exceptions=True)

    seen_ids: set[str] = set()
    raw_places: list[dict] = []
    errors: list[BaseException] = []
    for batch in all_results:
        if isinstance(batch, Exception):
            errors.append(batch)
            continue
        for place in batch:
            pid = place.get("place_id", "")
            if pid and pid not in seen_ids:
                seen_ids.add(pid)
                raw_places.append(place)
            elif not pid:
                raw_places.append(place)

    if not raw_places:
        if errors:
            raise errors[0]

        logger.info("Google Places returned no real results; no leads saved.")
        asyncio.create_task(_log_search_audit(user_id, workspace_id, request, 0, 0))
        return ExplorerSearchResponse(results=[], total=0, saved_new=0)

    # Process up to 10 places concurrently (semaphore-gated), Supabase calls in thread pool
    loop = asyncio.get_running_loop()
    tasks = [_process_place(place, workspace_id, request, loop) for place in raw_places]
    place_results = await asyncio.gather(*tasks, return_exceptions=True)

    results: list[ExplorerResultItem] = []
    process_errors: list[BaseException] = []
    saved_new = 0
    for res in place_results:
        if isinstance(res, Exception):
            process_errors.append(res)
            continue
        item, n = res
        if item is not None:
            results.append(item)
            saved_new += n

    if not results and process_errors:
        raise process_errors[0]

    asyncio.create_task(_log_search_audit(user_id, workspace_id, request, len(results), saved_new))
    logger.info("Explorer complete: %d results, %d new leads saved", len(results), saved_new)
    return ExplorerSearchResponse(results=results, total=len(results), saved_new=saved_new)
