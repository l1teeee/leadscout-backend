import hashlib
import json
import logging

import httpx

from app.cache import cache
from app.config import settings
from app.exceptions import ExternalServiceError
from app.services import social_scraper_service

logger = logging.getLogger(__name__)

_OPENAI_URL = "https://api.openai.com/v1/chat/completions"
_TIMEOUT = 30.0
_BRAND_CLASSIFICATION_TTL = 7 * 24 * 60 * 60
_OPENAI_READY_CACHE_KEY = "ai:openai-ready"
_OPENAI_READY_TTL = 5 * 60

_http: httpx.AsyncClient | None = None


def _get_http() -> httpx.AsyncClient:
    global _http
    if _http is None:
        _http = httpx.AsyncClient(
            timeout=_TIMEOUT,
            limits=httpx.Limits(
                max_connections=5,
                max_keepalive_connections=3,
                keepalive_expiry=30.0,
            ),
        )
    return _http


def _brand_classification_key(place: dict) -> str:
    raw = "|".join(
        str(place.get(key) or "").strip().lower()
        for key in ("place_id", "name", "formatted_address", "website", "formatted_phone_number")
    )
    return f"ai:brand-classification:{hashlib.sha256(raw.encode()).hexdigest()[:32]}"


def _build_prompt(lead: dict) -> str:
    issues = ", ".join(lead.get("issues", [])) or "Ninguna detectada"
    phone = lead.get("phone") or "No tiene"
    website = lead.get("website") or "No tiene"
    social_scrape = lead.get("social_scrape") or {}
    social_profiles = social_scrape.get("profiles") or []
    social_status = social_scrape.get("status") or "not_checked"
    social_reason = social_scrape.get("reason") or ""
    social_lines = (
        "\n".join(f"- {profile.get('platform')}: {profile.get('url')}" for profile in social_profiles)
        if social_profiles
        else "No se detectaron perfiles sociales en el scraping del sitio web."
    )
    return f"""Eres un experto en marketing digital y ventas B2B para pequeñas empresas en Latinoamérica.

Analiza este negocio y da recomendaciones específicas y accionables:

Nombre: {lead.get("name", "N/A")}
Categoría: {lead.get("category", "N/A")}
Ubicación: {lead.get("location", "N/A")}
Teléfono: {phone}
Sitio web: {website}
Score digital: {lead.get("score", 0)}/100
Brechas detectadas: {issues}
Estado del scraping de redes sociales: {social_status} ({social_reason})
Redes sociales detectadas:
{social_lines}

Reglas importantes:
- Si hay redes sociales detectadas, NO recomiendes crear redes sociales desde cero. Recomienda optimizar, auditar o activar mejor esos perfiles.
- Si el scraping falló o no se pudo revisar, no afirmes que no tiene redes. Indica que se debe validar manualmente antes de proponer creación de perfiles.
- Si no se detectan redes después de un scraping exitoso, puedes recomendar crear o completar perfiles sociales, pero aclara que la evidencia revisada fue el sitio web disponible.

Responde en este formato exacto (sin markdown extra, sin asteriscos):

ANÁLISIS
[2-3 oraciones sobre la situación digital actual del negocio]

RECOMENDACIONES
1. [Recomendación concreta]
2. [Recomendación concreta]
3. [Recomendación concreta]

ESTRATEGIA DE PRIMER CONTACTO
[Cómo abordar este lead en 2-3 oraciones]"""


async def enrich_lead_for_analysis(lead: dict) -> dict:
    social_scrape = await social_scraper_service.detect_social_profiles(lead.get("website"))
    return {**lead, "social_scrape": social_scrape}


async def analyze_lead(lead: dict) -> str:
    if not settings.openai_configured:
        raise ValueError("OPENAI_API_KEY no está configurado en .env")

    enriched_lead = await enrich_lead_for_analysis(lead)
    prompt = _build_prompt(enriched_lead)

    resp = await _get_http().post(
        _OPENAI_URL,
        json={
            "model": settings.OPENAI_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 600,
            "temperature": 0.6,
        },
        headers={
            "Authorization": f"Bearer {settings.OPENAI_API_KEY.get_secret_value()}",
            "Content-Type": "application/json",
        },
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"].strip()


def _brand_classification_messages(place: dict) -> list[dict[str, str]]:
    payload = {
        "name": place.get("name"),
        "category": place.get("category"),
        "address": place.get("formatted_address"),
        "location": place.get("location"),
        "phone": place.get("formatted_phone_number"),
        "website": place.get("website"),
        "google_place_id": place.get("place_id"),
    }
    return [
        {
            "role": "system",
            "content": (
                "You classify Google Places businesses for a lead generation product. "
                "The product must keep only local independent small businesses, entrepreneurs, "
                "local service providers, neighborhood stores, clinics, salons, restaurants, "
                "workshops, and SMBs. Mark as ineligible if the business appears to be a "
                "recognized national or international brand, franchise, corporate chain, bank, "
                "telecom, supermarket chain, gas station chain, mall/branch of a large retailer, "
                "government/public institution, marketplace, or if the evidence is unclear. "
                "Be conservative: unknown or ambiguous corporate-looking brands are not eligible. "
                "Return only valid JSON."
            ),
        },
        {
            "role": "user",
            "content": (
                "Classify this business. Return exactly this JSON shape: "
                '{"eligible_local_business": boolean, "classification": '
                '"local_independent|recognized_brand|chain|franchise|institution|unclear", '
                '"confidence": number, "reason": string}. '
                f"Business data: {json.dumps(payload, ensure_ascii=False)}"
            ),
        },
    ]


def _parse_brand_classification(content: str) -> dict:
    data = json.loads(content)
    classification = str(data.get("classification") or "unclear")
    reason = str(data.get("reason") or "No reason returned.")[:300]
    try:
        confidence = float(data.get("confidence") or 0)
    except (TypeError, ValueError):
        confidence = 0.0

    return {
        "eligible_local_business": bool(data.get("eligible_local_business")),
        "classification": classification,
        "confidence": max(0.0, min(confidence, 1.0)),
        "reason": reason,
    }


def _openai_response_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
        error = payload.get("error") if isinstance(payload, dict) else None
        if isinstance(error, dict) and error.get("message"):
            return str(error["message"])[:300]
        if isinstance(payload, dict) and payload.get("message"):
            return str(payload["message"])[:300]
    except (ValueError, TypeError):
        pass

    return response.text[:300] if response.text else ""


def _openai_status_message(response: httpx.Response) -> str:
    status_code = response.status_code
    detail = _openai_response_detail(response)

    if status_code == 401:
        return (
            "OPENAI_API_KEY is invalid or unauthorized. Update OPENAI_API_KEY in the "
            "backend .env and restart the backend."
        )
    if status_code == 403:
        return "OPENAI_API_KEY does not have permission to use the configured OpenAI project or model."
    if status_code == 404:
        return f"OPENAI_MODEL '{settings.OPENAI_MODEL}' is unavailable for this API key."
    if status_code == 429:
        return "OpenAI rate limit or quota was reached. Check billing, quota, or retry later."
    if status_code == 400:
        return (
            f"OpenAI rejected the validation request: {detail}"
            if detail
            else "OpenAI rejected the validation request. Check OPENAI_MODEL in the backend .env."
        )

    return (
        f"OpenAI request failed with HTTP {status_code}: {detail}"
        if detail
        else f"OpenAI request failed with HTTP {status_code}."
    )


async def validate_openai_ready() -> None:
    if not settings.openai_configured:
        raise ExternalServiceError(
            "OpenAI",
            "OPENAI_API_KEY is required to validate local businesses before saving leads.",
        )

    if await cache.get(_OPENAI_READY_CACHE_KEY):
        return

    try:
        resp = await _get_http().post(
            _OPENAI_URL,
            json={
                "model": settings.OPENAI_MODEL,
                "messages": [{"role": "user", "content": "Reply with OK."}],
                "max_tokens": 5,
                "temperature": 0,
            },
            headers={
                "Authorization": f"Bearer {settings.OPENAI_API_KEY.get_secret_value()}",
                "Content-Type": "application/json",
            },
        )
        resp.raise_for_status()
        await cache.set(_OPENAI_READY_CACHE_KEY, True, ttl=_OPENAI_READY_TTL)
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "OpenAI readiness check failed: status=%s detail=%s",
            exc.response.status_code,
            _openai_response_detail(exc.response),
        )
        raise ExternalServiceError("OpenAI", _openai_status_message(exc.response)) from exc
    except httpx.HTTPError as exc:
        logger.warning("OpenAI readiness check failed: %s", exc)
        raise ExternalServiceError(
            "OpenAI",
            "Could not reach OpenAI to validate local businesses. Check network or API availability.",
        ) from exc


async def classify_local_business_candidate(place: dict) -> dict:
    await validate_openai_ready()

    key = _brand_classification_key(place)
    cached = await cache.get(key)
    if cached is not None:
        return cached

    try:
        resp = await _get_http().post(
            _OPENAI_URL,
            json={
                "model": settings.OPENAI_MODEL,
                "messages": _brand_classification_messages(place),
                "max_tokens": 180,
                "temperature": 0,
                "response_format": {"type": "json_object"},
            },
            headers={
                "Authorization": f"Bearer {settings.OPENAI_API_KEY.get_secret_value()}",
                "Content-Type": "application/json",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"].strip()
        result = _parse_brand_classification(content)
        await cache.set(key, result, ttl=_BRAND_CLASSIFICATION_TTL)
        return result
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "OpenAI brand classification failed: status=%s detail=%s",
            exc.response.status_code,
            _openai_response_detail(exc.response),
        )
        raise ExternalServiceError("OpenAI", _openai_status_message(exc.response)) from exc
    except httpx.HTTPError as exc:
        logger.warning("OpenAI brand classification failed: %s", exc)
        raise ExternalServiceError(
            "OpenAI",
            "Could not reach OpenAI to validate whether a business is local.",
        ) from exc
    except (KeyError, json.JSONDecodeError) as exc:
        logger.warning("OpenAI brand classification returned invalid data: %s", exc)
        raise ExternalServiceError(
            "OpenAI",
            "OpenAI returned an invalid validation response. Check OPENAI_MODEL in the backend .env.",
        ) from exc
