import json
from collections.abc import Callable

_EXEMPT_PATHS = frozenset({
    "/health",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/docs/oauth2-redirect",
})

_SECURITY_HEADERS = [
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"strict-origin-when-cross-origin"),
]

_403_BODY = json.dumps({"detail": "Origin not allowed."}).encode()


class OriginGuardMiddleware:
    """
    Pure-ASGI middleware.  When a browser sends an Origin header that is not
    in the whitelist, the request is rejected with 403 before auth runs.

    Requests without an Origin header (server-to-server, health checks, curl)
    are always passed through — this guard targets browser-based cross-origin
    abuse, not legitimate programmatic callers.

    Exempt paths bypass the check even when Origin is present.
    """

    def __init__(self, app, allowed_origins: frozenset[str]) -> None:
        self.app = app
        self.allowed_origins = allowed_origins

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path: str = scope.get("path", "")
        if path in _EXEMPT_PATHS:
            await self.app(scope, receive, send)
            return

        origin: str = ""
        for name, value in scope.get("headers", []):
            if name == b"origin":
                origin = value.decode("latin-1")
                break

        # No Origin header → server-to-server call → pass through
        if not origin:
            await self.app(scope, receive, send)
            return

        if origin not in self.allowed_origins:
            await _send_403(send)
            return

        await self.app(scope, receive, send)


async def _send_403(send: Callable) -> None:
    await send({
        "type": "http.response.start",
        "status": 403,
        "headers": [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(_403_BODY)).encode()),
            *_SECURITY_HEADERS,
        ],
    })
    await send({
        "type": "http.response.body",
        "body": _403_BODY,
        "more_body": False,
    })
