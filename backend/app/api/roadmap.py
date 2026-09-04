from fastapi import APIRouter, Request

from backend.app.curriculum.service import CurriculumService, RoadmapView
from backend.app.learner.service import LearnerStateService

router = APIRouter(prefix="/roadmap", tags=["roadmap"])


@router.get("", response_model=RoadmapView)
def get_roadmap(request: Request) -> RoadmapView:
    service: CurriculumService = request.app.state.curriculum_service
    learner_service: LearnerStateService = request.app.state.learner_state_service
    return service.roadmap_view(learner_service.roadmap_state_map())
