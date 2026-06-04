import logging
import re

from app.repositories import leads_repository
from app.config import settings
from app.schemas.explorer_schema import ExplorerResultItem, ExplorerSearchRequest, ExplorerSearchResponse
from app.services import places_service, scoring_service

logger = logging.getLogger(__name__)


def _priority_from_score(score: int) -> str:
    if score <= 20:
        return "alta"
    if score <= 40:
        return "media"
    return "baja"


async def search_and_save(workspace_id: str, request: ExplorerSearchRequest) -> ExplorerSearchResponse:
    logger.info(
        "Explorer search: query=%s location=%s radius=%.1fkm",
        request.query, request.location, request.radius_km,
    )
    radius_m = int(request.radius_km * 1000)
    raw_places = await places_service.search_places(
        request.query,
        request.location,
        radius_m,
        request.latitude,
        request.longitude,
    )

    if not raw_places:
        if settings.MOCK_PLACES_ENABLED:
            logger.info("Google Places returned no usable results - using localized mock results for dev")
            results, saved_new = _mock_results_and_save(
                workspace_id=workspace_id,
                query=request.query,
                location=request.location,
                category=request.category,
                latitude=request.latitude,
                longitude=request.longitude,
            )
            return ExplorerSearchResponse(results=results, total=len(results), saved_new=saved_new)

        logger.info("Google Places returned no real results; no leads saved.")
        return ExplorerSearchResponse(results=[], total=0, saved_new=0)

    results: list[ExplorerResultItem] = []
    saved_new = 0

    for place in raw_places:
        place_id = place.get("place_id", "")
        place_resource_name = place.get("place_resource_name") or place_id
        details = await places_service.get_place_details(place_resource_name) if place_resource_name else {}
        place_data = {**place, **details}
        existing = leads_repository.find_by_place_id(place_id) if place_id else None

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

        geo = place_data.get("geometry", {}).get("location", {})
        item = ExplorerResultItem(
            google_place_id=place_id,
            name=place_data.get("name", ""),
            category=request.category,
            address=place_data.get("formatted_address"),
            location=request.location,
            latitude=geo.get("lat"),
            longitude=geo.get("lng"),
            phone=place_data.get("formatted_phone_number"),
            website=place_data.get("website"),
            score=score,
            issues=issues,
            already_saved=existing is not None,
        )
        results.append(item)

        if not existing and place_id:
            leads_repository.create_lead(workspace_id, {
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
            })
            saved_new += 1

    logger.info("Explorer complete: %d results, %d new leads saved", len(results), saved_new)
    return ExplorerSearchResponse(results=results, total=len(results), saved_new=saved_new)


_MOCK_STREETS = [
    "Av. Principal",
    "Calle Central",
    "Boulevard Norte",
    "Calle Comercio",
    "Av. Independencia",
    "Pasaje Mercado",
]

_MOCK_NAMES = [
    "Mercado Central",
    "Comercial La Esquina",
    "Servicios del Centro",
    "Casa Profesional",
    "Punto Local",
    "Negocio Express",
]

_KNOWN_CENTERS: dict[str, tuple[float, float]] = {
    "salta": (-24.7829, -65.4117),
    "san salvador": (13.6929, -89.2182),
    "santa tecla": (13.6731, -89.2891),
    "antiguo cuscatlan": (13.6736, -89.2402),
    "guatemala": (14.6349, -90.5069),
    "tegucigalpa": (14.0723, -87.1921),
    "san jose": (9.9281, -84.0907),
    "panama": (8.9824, -79.5199),
    "ciudad de mexico": (19.4326, -99.1332),
    "bogota": (4.7110, -74.0721),
    "lima": (-12.0464, -77.0428),
    "santiago": (-33.4489, -70.6693),
    "buenos aires": (-34.6037, -58.3816),
}


def _normalize(value: str) -> str:
    import unicodedata

    text = unicodedata.normalize("NFD", value)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return text.lower().strip()


def _location_label(location: str) -> str:
    match = re.search(r"\(([^)]+)\)", location)
    if match:
        return match.group(1).strip()
    return location.split(",")[0].strip() or "la zona seleccionada"


def _mock_center(location: str, latitude: float | None, longitude: float | None) -> tuple[float, float]:
    if latitude is not None and longitude is not None:
        return latitude, longitude

    normalized = _normalize(location)
    for key, center in _KNOWN_CENTERS.items():
        if key in normalized:
            return center

    return 13.6929, -89.2182


def _phone_prefix(location: str) -> str:
    normalized = _normalize(location)
    if "salta" in normalized or "argentina" in normalized:
        return "+54 387"
    if "guatemala" in normalized:
        return "+502"
    if "honduras" in normalized or "tegucigalpa" in normalized:
        return "+504"
    if "costa rica" in normalized or "san jose" in normalized:
        return "+506"
    if "panama" in normalized:
        return "+507"
    if "mexico" in normalized:
        return "+52"
    if "colombia" in normalized or "bogota" in normalized:
        return "+57"
    if "peru" in normalized or "lima" in normalized:
        return "+51"
    if "chile" in normalized or "santiago" in normalized:
        return "+56"
    return "+503"


def _display_query(query: str) -> str:
    normalized = _normalize(query)
    if normalized in {"todas", "todos", "all", "general", "negocios locales"}:
        return "Negocio local"
    return query.title()


def _category_label(category: str) -> str:
    normalized = _normalize(category)
    if normalized in {"todas", "todos", "all", "general"}:
        return "Comercio local"
    return category


def _mock_results_and_save(
    workspace_id: str,
    query: str,
    location: str,
    category: str,
    latitude: float | None,
    longitude: float | None,
) -> tuple[list[ExplorerResultItem], int]:
    """Generate dev results around the requested search area and save them."""
    import hashlib

    results: list[ExplorerResultItem] = []
    saved_new = 0
    base_lat, base_lng = _mock_center(location, latitude, longitude)
    location_label = _location_label(location)
    phone_prefix = _phone_prefix(location)
    display_query = _display_query(query)
    category_display = _category_label(category)

    for i in range(6):
        street = _MOCK_STREETS[i % len(_MOCK_STREETS)]
        business_name = _MOCK_NAMES[i % len(_MOCK_NAMES)]
        number = (i + 1) * 100
        lat = base_lat + ((i % 3) - 1) * 0.0045
        lng = base_lng + ((i // 3) - 0.5) * 0.0045

        raw = f"{query.lower().strip()}|{location.lower().strip()}|{base_lat:.5f}|{base_lng:.5f}|{i}"
        place_id = "mock-" + hashlib.md5(raw.encode()).hexdigest()[:12]

        has_phone = i % 3 != 0
        has_website = i % 2 != 0
        phone = f"{phone_prefix} {4000 + i * 137:04d}-{1000 + i * 113:04d}" if has_phone else None
        website = f"https://negocio-local-{i + 1}.com" if has_website else None

        score, issues = scoring_service.calculate_score(
            has_website=has_website,
            has_phone=has_phone,
            has_rating=i % 4 != 0,
            website_has_ssl=False,
            pagespeed_score=None,
            has_complete_google_business=has_phone and i % 4 != 0,
        )

        existing = leads_repository.find_by_place_id(place_id)
        item = ExplorerResultItem(
            google_place_id=place_id,
            name=f"{display_query} {business_name} {i + 1}",
            category=category_display,
            address=f"{street} {number}, {location_label}",
            location=location_label,
            latitude=lat,
            longitude=lng,
            phone=phone,
            website=website,
            score=score,
            issues=issues,
            already_saved=existing is not None,
        )
        results.append(item)

        if not existing:
            leads_repository.create_lead(workspace_id, {
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
            })
            saved_new += 1

    logger.info("Mock search '%s' en '%s': %d resultados, %d guardados", query, location, len(results), saved_new)
    return results, saved_new
