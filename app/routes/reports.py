from datetime import date

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel

from app.config import settings
from app.dependencies import CurrentUser, CurrentWorkspace
from app.services import email_service, report_export_service, reports_service

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/summary")
async def get_summary(workspace_id: CurrentWorkspace):
    return await reports_service.get_summary(workspace_id)


@router.get("/timeline")
async def get_timeline(
    workspace_id: CurrentWorkspace,
    days: int = Query(default=30, ge=7, le=90),
    all: bool = Query(default=False),
):
    if all:
        return await reports_service.get_timeline_all(workspace_id)
    return await reports_service.get_timeline(workspace_id, days)


@router.get("/export")
async def export_report(
    workspace_id: CurrentWorkspace,
    user: CurrentUser,
    format: str = Query(default="pdf", pattern="^(pdf|xlsx)$"),
    days: int = Query(default=30, ge=7, le=90),
):
    days = days if days in (7, 30, 90) else 30
    summary = await reports_service.get_summary(workspace_id)
    timeline = await reports_service.get_timeline(workspace_id, days)
    period_label = f"Últimos {days} días"
    today_str = date.today().isoformat()

    if format == "pdf":
        meta = {
            "workspace_name": user.workspace_name or "",
            "full_name": user.full_name or user.email,
            "generated_date": today_str,
            "period_label": period_label,
            "high_opportunity": 0,
        }
        pdf_bytes = report_export_service.build_pdf(summary, timeline, meta)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="scoutia-report-{today_str}.pdf"'
            },
        )
    else:
        xlsx_bytes = report_export_service.build_xlsx(summary, timeline)
        return Response(
            content=xlsx_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f'attachment; filename="scoutia-report-{today_str}.xlsx"'
            },
        )


class EmailReportBody(BaseModel):
    days: int = 30


@router.post("/email")
async def email_report(
    workspace_id: CurrentWorkspace,
    user: CurrentUser,
    body: EmailReportBody = EmailReportBody(),
):
    days = body.days if body.days in (7, 30, 90) else 30

    if not settings.BREVO_API_KEY.get_secret_value():
        raise HTTPException(status_code=503, detail="Email no está configurado")

    summary = await reports_service.get_summary(workspace_id)
    timeline = await reports_service.get_timeline(workspace_id, days)
    period_label = f"Últimos {days} días"
    today_str = date.today().isoformat()

    meta = {
        "workspace_name": user.workspace_name or "",
        "full_name": user.full_name or user.email,
        "generated_date": today_str,
        "period_label": period_label,
        "high_opportunity": 0,
    }
    pdf_bytes = report_export_service.build_pdf(summary, timeline, meta)

    await email_service.send_report_email(
        to_email=user.email,
        to_name=user.full_name,
        pdf_bytes=pdf_bytes,
        period_label=period_label,
        workspace_name=user.workspace_name,
    )
    return {"sent": True, "to": user.email}
