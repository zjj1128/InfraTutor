from __future__ import annotations

import asyncio

from backend.app.core.config import PROJECT_ROOT, get_settings
from backend.app.curriculum.loader import load_curriculum
from backend.app.db.session import (
    create_database_engine,
    create_session_factory,
    initialize_database,
)
from backend.app.learner.service import LearnerStateService
from backend.app.llm.application import TutorTurnService
from backend.app.llm.builders import AssessmentRequestBuilder, TeacherRequestBuilder
from backend.app.llm.contracts import LearnerTurn, LearnerTurnKind
from backend.app.llm.factory import create_llm_gateway
from backend.app.llm.prompt_loader import PromptLoader
from backend.app.llm.services import AssessorService, TeacherService
from backend.app.llm.validation import AssessmentSemanticValidator
from backend.app.tutor.engine import TutorEngine


async def run_smoke() -> int:
    settings = get_settings()
    missing = []
    if settings.llm_mode != "live":
        missing.append("LLM_MODE=live")
    if not settings.llm_api_key:
        missing.append("LLM_API_KEY")
    if not settings.llm_assessor_model:
        missing.append("LLM_ASSESSOR_MODEL")
    if not settings.llm_teacher_model:
        missing.append("LLM_TEACHER_MODEL")
    if missing:
        print("Live smoke 未运行；缺少配置: " + ", ".join(missing))
        return 0

    catalog = load_curriculum(settings.curriculum_dir or PROJECT_ROOT / "curriculum")
    database = create_database_engine("sqlite://")
    initialize_database(database)
    session_factory = create_session_factory(database)
    learner = LearnerStateService(catalog, session_factory)
    learner.ensure_default_learner()
    learner.reset("golden_path")
    tutor = TutorEngine(catalog, session_factory, learner)
    prompt_loader = PromptLoader()
    prompt_loader.load_all()
    gateway = create_llm_gateway(settings, prompt_loader)
    service = TutorTurnService(
        tutor_engine=tutor,
        learner_state=learner,
        assessor=AssessorService(
            settings,
            gateway,
            AssessmentRequestBuilder(catalog),
            AssessmentSemanticValidator(catalog),
        ),
        teacher=TeacherService(settings, gateway),
        teacher_builder=TeacherRequestBuilder(catalog),
        session_factory=session_factory,
    )
    started = tutor.start_session("memory_registration")
    result = await service.handle_turn(
        started.session.session_id,
        LearnerTurn(
            kind=LearnerTurnKind.ANSWER,
            text=(
                "Memory Registration 不会复制 payload；数据仍在主机内存，注册负责稳定、映射和保护。"
            ),
            client_turn_id="live_smoke_turn_1",
            submitted_at=started.session.created_at,
        ),
    )
    if result.recoverable_error:
        print(f"Live smoke 失败: {result.recoverable_error.code.value}")
        return 1
    operations = ", ".join(item.operation.value for item in result.llm_metadata)
    print(f"Live smoke 通过: schema+semantic validation; operations={operations}")
    database.dispose()
    return 0


def main() -> int:
    return asyncio.run(run_smoke())


if __name__ == "__main__":
    raise SystemExit(main())
