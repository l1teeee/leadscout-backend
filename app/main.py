import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

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
from app.middleware.origin_guard import OriginGuardMiddleware
from app.middleware.request_logger import RequestLoggerMiddleware
from app.rate_limit import limiter
from app.routes import auth, explorer, health, leads, reports
from app.routes import settings as settings_router

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.services import supabase_service
    supabase_service.initialize()
    logger.info("Starting %s [%s]", settings.APP_NAME, settings.APP_ENV)
    logger.info("Cache: %s", cache)
    logger.info("Supabase: %s", "connected" if settings.supabase_configured else "not configured")
    logger.info("Google Places: %s", "enabled" if settings.google_places_configured else "disabled")
    yield
    await cache.close()
    logger.info("Shutting down %s", settings.APP_NAME)


_is_prod = settings.APP_ENV == "production"
app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    lifespan=lifespan,
    docs_url=None if _is_prod else "/docs",
    redoc_url=None if _is_prod else "/redoc",
    openapi_url=None if _is_prod else "/openapi.json",
)

# ── Rate limiting ─────────────────────────────────────────────────────────────
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

# ── Security headers (innermost — runs after route handler returns) ───────────
@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    if settings.APP_ENV == "production":
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    return response

# ── Middleware stack (last added = outermost = runs first on inbound request) ─
# Request flow: RequestLogger → OriginGuard → CORS → SecurityHeaders → router

# CORS: handles OPTIONS preflight and injects Access-Control-* headers.
# expose_headers allows the browser JS to read X-Request-ID from responses.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Requested-With"],
    expose_headers=["X-Request-ID"],
)

# Origin guard: rejects browser requests from unauthorized origins before auth.
# Server-to-server calls (no Origin header) always pass through.
app.add_middleware(
    OriginGuardMiddleware,
    allowed_origins=settings.allowed_origins_set,
)

# Request logger: outermost layer — captures every request including rejections.
# Assigns X-Request-ID, logs method/path/status/duration/ip/user_id.
app.add_middleware(RequestLoggerMiddleware)

# ── Domain exceptions → HTTP responses ───────────────────────────────────────
app.add_exception_handler(LeadNotFoundError, lead_not_found_handler)  # type: ignore[arg-type]
app.add_exception_handler(DuplicateLeadError, duplicate_lead_handler)  # type: ignore[arg-type]
app.add_exception_handler(ExternalServiceError, external_service_handler)  # type: ignore[arg-type]

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(health.router)
app.include_router(auth.router, prefix="/api")
app.include_router(leads.router, prefix="/api")
app.include_router(explorer.router, prefix="/api")
app.include_router(reports.router, prefix="/api")
app.include_router(settings_router.router, prefix="/api")
