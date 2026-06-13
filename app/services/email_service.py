import httpx
from app.config import settings

_BREVO_URL = "https://api.brevo.com/v3/smtp/email"
_http: httpx.AsyncClient | None = None


def _get_http() -> httpx.AsyncClient:
    global _http
    if _http is None:
        _http = httpx.AsyncClient(timeout=15.0)
    return _http


async def send_transactional_email(
    to_email: str,
    to_name: str | None,
    subject: str,
    html_content: str,
    text_content: str | None = None,
) -> None:
    payload = {
        "sender": {
            "email": settings.BREVO_SENDER_EMAIL,
            "name": settings.BREVO_SENDER_NAME,
        },
        "to": [{"email": to_email, **({"name": to_name} if to_name else {})}],
        "subject": subject,
        "htmlContent": html_content,
    }
    if text_content:
        payload["textContent"] = text_content

    resp = await _get_http().post(
        _BREVO_URL,
        json=payload,
        headers={
            "api-key": settings.BREVO_API_KEY.get_secret_value(),
            "Content-Type": "application/json",
        },
    )
    resp.raise_for_status()
