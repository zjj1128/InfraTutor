from fastapi import APIRouter, Request

from backend.app.learner.schemas import LearnerView, ResetLearnerRequest
from backend.app.learner.service import LearnerStateService

learner_router = APIRouter(prefix="/learner", tags=["learner"])
demo_router = APIRouter(prefix="/demo", tags=["development"])


@learner_router.get("", response_model=LearnerView)
def get_learner(request: Request) -> LearnerView:
    service: LearnerStateService = request.app.state.learner_state_service
    return service.get_learner()


@demo_router.post("/reset", response_model=LearnerView)
def reset_learner(payload: ResetLearnerRequest, request: Request) -> LearnerView:
    service: LearnerStateService = request.app.state.learner_state_service
    return service.reset(payload.seed)
