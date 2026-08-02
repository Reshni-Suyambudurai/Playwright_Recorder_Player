"""Validation discovery API endpoints."""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from app.models.validation import ValidationDiscoveryRequest
from app.services.browser_service import BrowserService
from app.services.session_manager import SessionManager
from app.services.validation_service import ValidationService
from app.utils import tab_manager

logger = logging.getLogger("playwright_recorder.api.validation")


class ValidationAPI:
    def __init__(self, session_manager: SessionManager, browser_service: BrowserService, validation_service: ValidationService):
        self.session_manager = session_manager
        self.browser_service = browser_service
        self.validation_service = validation_service

    async def discover(self, request: ValidationDiscoveryRequest) -> dict:
        session = self.session_manager.get_session(request.session_id)
        if not session or not session.page:
            raise HTTPException(status_code=404, detail={"success": False, "error": "Session not found", "status": "No active session or page"})

        page = tab_manager.get_active_page(session) or session.page
        try:
            if request.selector:
                discovery = await self.validation_service.discover_from_selector(page, request.selector)
            elif request.x is not None and request.y is not None:
                discovery = await self.validation_service.discover_from_point(page, request.x, request.y)
            else:
                raise HTTPException(status_code=400, detail={"success": False, "error": "selector or x/y coordinates are required", "status": "Invalid validation request"})
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("Validation discovery failed for session %s: %s", request.session_id, exc, exc_info=True)
            raise HTTPException(status_code=500, detail={"success": False, "error": str(exc), "status": "Validation discovery failed"})

        return {"success": True, "data": discovery.model_dump(by_alias=True)}

    async def catalog(self) -> dict:
        catalog = self.validation_service.get_catalog()
        return {"success": True, "data": catalog.model_dump(by_alias=True)}


def create_validation_router(session_manager: SessionManager, browser_service: BrowserService, validation_service: ValidationService) -> APIRouter:
    router = APIRouter()
    api = ValidationAPI(session_manager, browser_service, validation_service)

    @router.post("/discover")
    async def discover(request: ValidationDiscoveryRequest):
        return await api.discover(request)

    @router.get("/catalog")
    async def get_catalog():
        return await api.catalog()

    return router
