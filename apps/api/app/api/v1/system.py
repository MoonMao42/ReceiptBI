"""系统能力 API"""

from hmac import compare_digest
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db import get_db
from app.models import APIResponse, SystemCapabilities
from app.services.app_settings import detect_system_capabilities, get_or_create_app_settings

router = APIRouter(prefix="/system", tags=["system"])
DESKTOP_SHUTDOWN_GRACE_SECONDS = 1.5


def _is_loopback_request(request: Request) -> bool:
    return request.client is not None and request.client.host in {"127.0.0.1", "::1"}


@router.get("/capabilities", response_model=APIResponse[SystemCapabilities])
async def get_capabilities(db: AsyncSession = Depends(get_db)):
    """获取当前运行时能力状态"""
    settings_record = await get_or_create_app_settings(db)
    return APIResponse.ok(data=detect_system_capabilities(settings_record))


@router.post("/prepare-shutdown", response_model=APIResponse[dict[str, Any]])
async def prepare_desktop_shutdown(
    request: Request,
    desktop_control_token: str | None = Header(
        default=None,
        alias="X-ReceiptBI-Desktop-Control",
    ),
) -> APIResponse[dict[str, Any]]:
    """Cooperatively pause active work before the desktop kills its API process."""

    expected_token = settings.RECEIPTBI_DESKTOP_CONTROL_TOKEN
    if (
        not expected_token
        or not desktop_control_token
        or not _is_loopback_request(request)
        or not compare_digest(desktop_control_token, expected_token)
    ):
        # Hosted/browser deployments do not have this capability at all. A 404
        # also avoids turning the private token boundary into an auth oracle.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    # Import lazily to avoid coupling the ordinary system-capabilities route to
    # the chat router's process-local registry at module import time.
    from app.api.v1.chat import active_query_registry

    result = await active_query_registry.prepare_shutdown(DESKTOP_SHUTDOWN_GRACE_SECONDS)
    return APIResponse.ok(data=result, message="Desktop shutdown prepared")
