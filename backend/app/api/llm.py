from fastapi import APIRouter, Request

from backend.app.llm.contracts import LLMStatus

router = APIRouter(prefix="/llm", tags=["llm"])


@router.get("/status", response_model=LLMStatus)
def get_llm_status(request: Request) -> LLMStatus:
    return request.app.state.llm_status_service.get()
