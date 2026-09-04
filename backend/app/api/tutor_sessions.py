from fastapi import APIRouter, Request

from backend.app.sessions.schemas import (
    AbandonSessionRequest,
    StartSessionRequest,
    SubmitTurnRequest,
    TutorSessionSnapshot,
)
from backend.app.sessions.service import TutorSessionService

router = APIRouter(prefix="/tutor/sessions", tags=["tutor-sessions"])


@router.post("", response_model=TutorSessionSnapshot, response_model_exclude_none=True)
async def start_session(payload: StartSessionRequest, request: Request) -> TutorSessionSnapshot:
    service: TutorSessionService = request.app.state.tutor_session_service
    return await service.start_or_resume(payload)


@router.get(
    "/active",
    response_model=TutorSessionSnapshot | None,
    response_model_exclude_none=True,
)
def get_active_session(request: Request) -> TutorSessionSnapshot | None:
    service: TutorSessionService = request.app.state.tutor_session_service
    return service.get_active()


@router.get(
    "/{session_id}",
    response_model=TutorSessionSnapshot,
    response_model_exclude_none=True,
)
def get_session(session_id: str, request: Request) -> TutorSessionSnapshot:
    service: TutorSessionService = request.app.state.tutor_session_service
    return service.get_snapshot(session_id)


@router.post(
    "/{session_id}/turns",
    response_model=TutorSessionSnapshot,
    response_model_exclude_none=True,
)
async def submit_turn(
    session_id: str,
    payload: SubmitTurnRequest,
    request: Request,
) -> TutorSessionSnapshot:
    service: TutorSessionService = request.app.state.tutor_session_service
    return await service.submit_turn(session_id, payload)


@router.post(
    "/{session_id}/abandon",
    response_model=TutorSessionSnapshot,
    response_model_exclude_none=True,
)
def abandon_session(
    session_id: str,
    payload: AbandonSessionRequest,
    request: Request,
) -> TutorSessionSnapshot:
    service: TutorSessionService = request.app.state.tutor_session_service
    return service.abandon(session_id, payload)
