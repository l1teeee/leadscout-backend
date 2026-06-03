import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.cache import cache
from app.config import settings
from app.exceptions import (
    DuplicateLeadError,
    ExternalServiceError,
    LeadNotFoundError,
    duplicate_lead_handler,
    external_service_handler,
    lead_not_found_handler,
)
from app.routes import auth, explorer, health, leads, reports
from app.routes import settings as settings_router

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s [%s]", settings.APP_NAME, settings.APP_ENV)
    logger.info("Cache: %s", cache)
    logger.info("Supabase: %s", "connected" if settings.supabase_configured else "mock mode")
    logger.info("Google Places: %s", "enabled" if settings.google_places_configured else "disabled")
    yield
    await cache.close()
    logger.info("Shutting down %s", settings.APP_NAME)


app = FastAPI(title=settings.APP_NAME, version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(LeadNotFoundError, lead_not_found_handler)  # type: ignore[arg-type]
app.add_exception_handler(DuplicateLeadError, duplicate_lead_handler)  # type: ignore[arg-type]
app.add_exception_handler(ExternalServiceError, external_service_handler)  # type: ignore[arg-type]

app.include_router(health.router)
app.include_router(auth.router, prefix="/api")
app.include_router(leads.router, prefix="/api")
app.include_router(explorer.router, prefix="/api")
app.include_router(reports.router, prefix="/api")
app.include_router(settings_router.router, prefix="/api")
