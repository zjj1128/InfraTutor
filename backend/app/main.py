from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.app.api.learner import demo_router, learner_router
from backend.app.api.llm import router as llm_router
from backend.app.api.roadmap import router as roadmap_router
from backend.app.api.tutor_sessions import router as tutor_sessions_router
from backend.app.core.config import Settings, get_settings
from backend.app.curriculum.loader import load_curriculum
from backend.app.curriculum.service import CurriculumService
from backend.app.db.session import (
    create_database_engine,
    create_session_factory,
    initialize_database,
)
from backend.app.learner.service import LearnerStateService
from backend.app.llm.application import TutorTurnService
from backend.app.llm.builders import AssessmentRequestBuilder, TeacherRequestBuilder
from backend.app.llm.factory import create_llm_gateway
from backend.app.llm.prompt_loader import PromptLoader
from backend.app.llm.services import AssessorService, TeacherService
from backend.app.llm.status import LLMStatusService
from backend.app.llm.validation import AssessmentSemanticValidator
from backend.app.sessions.errors import TutorSessionError
from backend.app.sessions.service import TutorSessionService
from backend.app.tutor.engine import TutorEngine


def create_app(settings: Settings | None = None) -> FastAPI:
    application_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        catalog = load_curriculum(application_settings.curriculum_dir)
        prompt_loader = PromptLoader()
        prompt_loader.load_all()
        engine = create_database_engine(application_settings.database_url)
        initialize_database(engine)
        session_factory = create_session_factory(engine)
        learner_state_service = LearnerStateService(catalog, session_factory)
        learner_state_service.ensure_default_learner()
        application.state.curriculum_service = CurriculumService(catalog)
        application.state.learner_state_service = learner_state_service
        tutor_engine = TutorEngine(catalog, session_factory, learner_state_service)
        gateway = create_llm_gateway(application_settings, prompt_loader)
        assessor_service = AssessorService(
            application_settings,
            gateway,
            AssessmentRequestBuilder(catalog),
            AssessmentSemanticValidator(catalog),
        )
        teacher_service = TeacherService(application_settings, gateway)
        application.state.tutor_engine = tutor_engine
        application.state.llm_gateway = gateway
        application.state.tutor_turn_service = TutorTurnService(
            tutor_engine=tutor_engine,
            learner_state=learner_state_service,
            assessor=assessor_service,
            teacher=teacher_service,
            teacher_builder=TeacherRequestBuilder(catalog),
            session_factory=session_factory,
        )
        application.state.tutor_session_service = TutorSessionService(
            settings=application_settings,
            catalog=catalog,
            session_factory=session_factory,
            learner_state=learner_state_service,
            tutor_engine=tutor_engine,
            assessor=assessor_service,
            teacher=teacher_service,
            teacher_builder=TeacherRequestBuilder(catalog),
        )
        application.state.llm_status_service = LLMStatusService(
            application_settings, session_factory
        )
        application.state.database_engine = engine
        application.state.database_session_factory = session_factory
        try:
            yield
        finally:
            await gateway.aclose()
            engine.dispose()

    application = FastAPI(
        title="InfraTutor API",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=application_settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.exception_handler(TutorSessionError)
    async def handle_session_error(_: Request, exc: TutorSessionError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code.value,
                    "message": exc.message,
                    **exc.details,
                }
            },
        )

    @application.get("/api/health", tags=["system"])
    def health() -> dict[str, str]:
        return {"status": "ok", "curriculum": "ready", "database": "ready"}

    application.include_router(roadmap_router, prefix="/api")
    application.include_router(learner_router, prefix="/api")
    application.include_router(demo_router, prefix="/api")
    application.include_router(llm_router, prefix="/api")
    application.include_router(tutor_sessions_router, prefix="/api")
    return application


app = create_app()
