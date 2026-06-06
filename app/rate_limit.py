import hashlib

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request


def _key_func(request: Request) -> str:
    """Use token hash when authenticated, remote IP otherwise."""
    auth = request.headers.get("Authorization", "")
    token = auth.removeprefix("Bearer ").strip()
    if token:
        return f"tok:{hashlib.sha256(token.encode()).hexdigest()[:24]}"
    return get_remote_address(request)


limiter = Limiter(key_func=_key_func)
