import base64
from datetime import date as _date

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


async def send_report_email(
    to_email: str,
    to_name: str | None,
    pdf_bytes: bytes,
    period_label: str,
    workspace_name: str | None = None,
) -> None:
    filename = f"scoutia-report-{_date.today().isoformat()}.pdf"
    subject = f"Tu reporte de Scoutia — {period_label}"
    ws = workspace_name or "tu workspace"
    html = f"""
    <div style="font-family:sans-serif;max-width:600px;margin:0 auto">
      <h2 style="color:#17110D">Tu reporte de Scoutia está listo</h2>
      <p>Hola {to_name or ""},</p>
      <p>Adjuntamos el reporte de leads de <strong>{ws}</strong> para el período: <strong>{period_label}</strong>.</p>
      <p>Encontrarás el detalle completo en el PDF adjunto.</p>
      <hr/>
      <p style="color:#888;font-size:12px">scoutia.dev — Reporte generado automáticamente</p>
    </div>
    """
    text = f"Tu reporte de Scoutia — {period_label}\nAdjunto el PDF con el detalle de leads de {ws}.\n\nscoutia.dev"
    payload = {
        "sender": {
            "email": settings.BREVO_SENDER_EMAIL,
            "name": settings.BREVO_SENDER_NAME,
        },
        "to": [{"email": to_email, **({"name": to_name} if to_name else {})}],
        "subject": subject,
        "htmlContent": html,
        "textContent": text,
        "attachment": [{"name": filename, "content": base64.b64encode(pdf_bytes).decode()}],
    }
    resp = await _get_http().post(
        _BREVO_URL,
        json=payload,
        headers={
            "api-key": settings.BREVO_API_KEY.get_secret_value(),
            "Content-Type": "application/json",
        },
    )
    resp.raise_for_status()
