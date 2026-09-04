from __future__ import annotations

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import func, select

from backend.app.core.config import Settings
from backend.app.curriculum.loader import load_curriculum
from backend.app.db.session import (
    create_database_engine,
    create_session_factory,
    initialize_database,
)
from backend.app.learner.models import Evidence
from backend.app.learner.service import LearnerStateService
from backend.app.llm.builders import AssessmentRequestBuilder, TeacherRequestBuilder
from backend.app.llm.factory import create_llm_gateway
from backend.app.llm.prompt_loader import PromptLoader
from backend.app.llm.services import AssessorService, TeacherService
from backend.app.llm.validation import AssessmentSemanticValidator
from backend.app.sessions.models import SessionMessage, TutorTurnRecord
from backend.app.sessions.schemas import StartSessionRequest, SubmitTurnRequest
from backend.app.sessions.service import TutorSessionService
from backend.app.tutor.engine import TutorEngine
from backend.app.tutor.models import DecisionTraceRecord


async def run_demo() -> None:
    with TemporaryDirectory(prefix="infratutor-session-demo-") as temporary_dir:
        settings = Settings(
            database_url=f"sqlite:///{Path(temporary_dir) / 'demo.db'}",
            llm_mode="mock",
            enable_debug_panel=True,
        )
        catalog = load_curriculum(settings.curriculum_dir)
        engine = create_database_engine(settings.database_url)
        initialize_database(engine)
        session_factory = create_session_factory(engine)
        learner_state = LearnerStateService(catalog, session_factory)
        learner_state.ensure_default_learner()
        learner_state.reset("golden_path")
        prompt_loader = PromptLoader()
        prompt_loader.load_all()
        gateway = create_llm_gateway(settings, prompt_loader)
        assessor = AssessorService(
            settings,
            gateway,
            AssessmentRequestBuilder(catalog),
            AssessmentSemanticValidator(catalog),
        )
        teacher = TeacherService(settings, gateway)
        tutor = TutorEngine(catalog, session_factory, learner_state)
        service = TutorSessionService(
            settings=settings,
            catalog=catalog,
            session_factory=session_factory,
            learner_state=learner_state,
            tutor_engine=tutor,
            assessor=assessor,
            teacher=teacher,
            teacher_builder=TeacherRequestBuilder(catalog),
        )

        snapshot = await service.start_or_resume(
            StartSessionRequest(
                target_node_id="memory_registration",
                entry_mode="diagnostic",
                client_request_id="demo-start",
            )
        )
        print("1. 创建 MR diagnostic Session")
        print(f"2. Tutor: {snapshot.messages[-1].text}")
        print(f"   Question: {snapshot.expected_question.question_id}")

        sequence: list[tuple[str, str | None]] = [
            ("MR 会把内存复制到 HCA。", None),
            ("CPU 负责配置 DMA 工作，DMA 引擎搬运数据，CPU 不执行逐字节复制，完成需要通知。", None),
            (
                "CPU 负责配置和提交，DMA 引擎搬运 payload，CPU 不逐字节复制，完成需要通知或轮询。",
                None,
            ),
            ("内存页需要保持稳定，映射不能失效，页固定不会复制数据。", None),
            ("", "stable"),
            (
                "页面保持稳定，地址映射供 HCA 使用，key 提供权限保护，数据仍在主机内存而不会复制。",
                None,
            ),
            ("key 与注册范围相关，HCA 会做权限和范围校验，不能任意访问。", None),
        ]
        final_request: SubmitTurnRequest | None = None
        for index, (text, option_id) in enumerate(sequence, start=1):
            question = snapshot.expected_question
            if question is None:
                raise RuntimeError("Golden Path 提前失去 expected question")
            request = SubmitTurnRequest(
                client_turn_id=f"demo-turn-{index}",
                expected_session_version=snapshot.version,
                expected_question_id=question.question_id,
                kind="ANSWER",
                text=text,
                selected_option_id=option_id,
            )
            snapshot = await service.submit_turn(snapshot.session_id, request)
            if index == 1:
                print(
                    f"3-5. Decision={snapshot.debug.final_action} "
                    f"current={snapshot.current_node.node_id}"
                )
                print(
                    f"     version={snapshot.version} "
                    f"return_stack={[item.node_id for item in snapshot.return_stack]}"
                )
            elif index == 3:
                print(f"6. DMA Mastered -> current={snapshot.current_node.node_id}")
            elif index == 5:
                print(f"7-8. Pinned Mastered -> current={snapshot.current_node.node_id}")
            elif index == 6:
                print(f"9. MR explanation -> next={snapshot.expected_question.question_id}")
            final_request = request

        print(f"10. MR status={snapshot.current_node.learner_status}")
        next_ready = snapshot.next_ready_node.node_id if snapshot.next_ready_node else "-"
        print(f"11. next Ready={next_ready}")
        with session_factory() as db:
            counts_before = (
                int(db.scalar(select(func.count()).select_from(TutorTurnRecord)) or 0),
                int(db.scalar(select(func.count()).select_from(SessionMessage)) or 0),
                int(db.scalar(select(func.count()).select_from(Evidence)) or 0),
                int(db.scalar(select(func.count()).select_from(DecisionTraceRecord)) or 0),
            )
        print(
            "12. counts "
            f"Turn={counts_before[0]} Message={counts_before[1]} "
            f"Evidence={counts_before[2]} Trace={counts_before[3]}"
        )
        if final_request is None:
            raise RuntimeError("Demo 没有生成最终 Turn")
        repeated = await service.submit_turn(snapshot.session_id, final_request)
        with session_factory() as db:
            counts_after = (
                int(db.scalar(select(func.count()).select_from(TutorTurnRecord)) or 0),
                int(db.scalar(select(func.count()).select_from(SessionMessage)) or 0),
                int(db.scalar(select(func.count()).select_from(Evidence)) or 0),
                int(db.scalar(select(func.count()).select_from(DecisionTraceRecord)) or 0),
            )
        print(
            f"13. duplicate replay session_version={repeated.version}, "
            f"counts_unchanged={counts_after == counts_before}"
        )
        print(f"    Decision Trace ID={snapshot.debug.decision_trace_id}")
        await gateway.aclose()
        engine.dispose()


def main() -> int:
    asyncio.run(run_demo())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
