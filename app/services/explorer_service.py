import logging
from uuid import uuid4

from app.repositories import leads_repository
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
    raw_places = await places_service.search_places(request.query, request.location, radius_m)

    if not raw_places:
        results = _mock_results(request.query, request.location, request.category)
        logger.info("Google Places not configured - returning %d mock results", len(results))
        return ExplorerSearchResponse(results=results, total=len(results), saved_new=0)

    results: list[ExplorerResultItem] = []
    saved_new = 0

    for place in raw_places:
        place_id = place.get("place_id", "")
        existing = leads_repository.find_by_place_id(place_id) if place_id else None

        has_website = bool(place.get("website"))
        has_phone = bool(place.get("formatted_phone_number"))
        has_rating = bool(place.get("rating"))

        score, issues = scoring_service.calculate_score(
            has_website=has_website,
            has_phone=has_phone,
            has_rating=has_rating,
            website_has_ssl=False,
            pagespeed_score=None,
            has_complete_google_business=has_rating and has_phone,
        )

        geo = place.get("geometry", {}).get("location", {})
        item = ExplorerResultItem(
            google_place_id=place_id,
            name=place.get("name", ""),
            category=request.category,
            address=place.get("formatted_address"),
            location=request.location,
            latitude=geo.get("lat"),
            longitude=geo.get("lng"),
            phone=place.get("formatted_phone_number"),
            website=place.get("website"),
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


def _mock_results(query: str, location: str, category: str) -> list[ExplorerResultItem]:
    return [
        ExplorerResultItem(
            google_place_id=f"mock-{uuid4()}",
            name=f"Negocio Demo {i + 1} ({query})",
            category=category,
            address=f"Calle Principal #{(i + 1) * 10}, {location}",
            location=location,
            latitude=13.6929 + i * 0.002,
            longitude=-89.2182 + i * 0.002,
            phone=None if i % 3 == 0 else f"+503 2{i}00-{i * 111:04d}",
            website=None if i % 2 == 0 else f"http://demo{i}.com",
            score=max(0, 85 - i * 15),
            issues=["Sin sitio web"] if i % 2 == 0 else [],
            already_saved=False,
        )
        for i in range(6)
    ]
