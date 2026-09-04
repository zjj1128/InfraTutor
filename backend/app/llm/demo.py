from __future__ import annotations

import asyncio
import json

from backend.app.core.config import PROJECT_ROOT, Settings
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
from backend.app.llm.mock_provider import MockLLMGateway
from backend.app.llm.prompt_loader import PromptLoader
from backend.app.llm.services import AssessorService, TeacherService
from backend.app.llm.validation import AssessmentSemanticValidator
from backend.app.tutor.engine import TutorEngine


def _dump(value: object) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")  # type: ignore[attr-defined]
    return json.dumps(value, ensure_ascii=False, indent=2)


async def run_demo() -> int:
    catalog = load_curriculum(PROJECT_ROOT / "curriculum")
    database = create_database_engine("sqlite://")
    initialize_database(database)
    session_factory = create_session_factory(database)
    learner = LearnerStateService(catalog, session_factory)
    learner.ensure_default_learner()
    learner.reset("golden_path")
    tutor = TutorEngine(catalog, session_factory, learner)
    prompt_loader = PromptLoader()
    prompt_loader.load_all()
    gateway = MockLLMGateway(prompt_loader)
    settings = Settings(database_url="sqlite://", llm_mode="mock", llm_provider="openai")
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
    turn = LearnerTurn(
        kind=LearnerTurnKind.ANSWER,
        text="MR 会把内存复制到 HCA。",
        client_turn_id="demo_llm_mock_turn_1",
        submitted_at=started.session.created_at,
    )
    result = await service.handle_turn(started.session.session_id, turn)

    print(f"1. 学生自然语言: {turn.text}")
    print("2. Mock Assessor 原始 Structured Output:")
    print(_dump(result.raw_assessment))
    print("3. 后端 canonical AssessmentResult:")
    print(_dump(result.validated_assessment))
    print(
        f"4. Tutor Engine Decision: {result.decision.action.value} {result.decision.target_node_id}"
    )
    print("5. TeacherDirective:")
    print(_dump(result.decision.teacher_directive))
    print("6. Mock Teacher Structured Output:")
    print(_dump(result.tutor_message))
    print(f"7. 最终中文消息: {result.tutor_message.student_message}")
    print("8. Learner State delta:")
    print(_dump(result.decision.state_delta))
    print("9. LLM metadata:")
    print(_dump([item.model_dump(mode="json") for item in result.llm_metadata]))
    print(f"10. Decision Trace ID: {result.decision_trace_id}")
    database.dispose()
    return 0


def main() -> int:
    return asyncio.run(run_demo())


if __name__ == "__main__":
    raise SystemExit(main())
