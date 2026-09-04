from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from backend.app.core.config import Settings
from backend.app.learner.models import Evidence
from backend.app.llm.contracts import LLMError, LLMErrorCode
from backend.app.llm.services import TeacherServiceResult
from backend.app.main import create_app
from backend.app.sessions.models import SessionMessage, TutorTurnRecord
from backend.app.tutor.models import DecisionTraceRecord


def _settings(tmp_path: Path, curriculum_copy: Path, **overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "database_url": f"sqlite:///{tmp_path / 'sessions.db'}",
        "curriculum_dir": curriculum_copy,
        "llm_mode": "mock",
        "enable_debug_panel": True,
    }
    values.update(overrides)
    return Settings(**values)


def _start(
    client: TestClient,
    node_id: str,
    mode: str,
) -> dict[str, Any]:
    response = client.post(
        "/api/tutor/sessions",
        json={
            "target_node_id": node_id,
            "entry_mode": mode,
            "client_request_id": str(uuid4()),
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _turn(
    client: TestClient,
    snapshot: dict[str, Any],
    *,
    kind: str = "ANSWER",
    text: str = "",
    option_id: str | None = None,
    client_turn_id: str | None = None,
) -> dict[str, Any]:
    response = client.post(
        f"/api/tutor/sessions/{snapshot['session_id']}/turns",
        json={
            "client_turn_id": client_turn_id or str(uuid4()),
            "expected_session_version": snapshot["version"],
            "expected_question_id": snapshot["expected_question"]["question_id"],
            "kind": kind,
            "text": text,
            "selected_option_id": option_id,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _counts(client: TestClient) -> tuple[int, int, int, int]:
    factory = client.app.state.database_session_factory
    with factory() as db:
        return (
            int(db.scalar(select(func.count()).select_from(TutorTurnRecord)) or 0),
            int(db.scalar(select(func.count()).select_from(SessionMessage)) or 0),
            int(db.scalar(select(func.count()).select_from(Evidence)) or 0),
            int(db.scalar(select(func.count()).select_from(DecisionTraceRecord)) or 0),
        )


def test_start_resume_conflict_abandon_and_start_new_target(
    tmp_path: Path, curriculum_copy: Path
) -> None:
    with TestClient(create_app(_settings(tmp_path, curriculum_copy))) as client:
        first = _start(client, "virtual_vs_physical_memory", "normal")
        assert first["status"] == "active"
        assert first["version"] == 1
        assert first["expected_question"]["node_id"] == "virtual_vs_physical_memory"

        resumed = _start(client, "virtual_vs_physical_memory", "normal")
        assert resumed["session_id"] == first["session_id"]
        assert len(resumed["messages"]) == 1

        conflict = client.post(
            "/api/tutor/sessions",
            json={
                "target_node_id": "memory_registration",
                "entry_mode": "diagnostic",
                "client_request_id": str(uuid4()),
            },
        )
        assert conflict.status_code == 409
        assert conflict.json()["error"]["code"] == "ACTIVE_SESSION_EXISTS"
        assert conflict.json()["error"]["active_session_id"] == first["session_id"]

        abandoned = client.post(
            f"/api/tutor/sessions/{first['session_id']}/abandon",
            json={"expected_session_version": first["version"]},
        )
        assert abandoned.status_code == 200
        assert abandoned.json()["status"] == "abandoned"
        second = _start(client, "memory_registration", "diagnostic")
        assert second["session_id"] != first["session_id"]


def test_start_rules_and_question_view_do_not_leak_answers(
    tmp_path: Path, curriculum_copy: Path
) -> None:
    with TestClient(create_app(_settings(tmp_path, curriculum_copy))) as client:
        locked = client.post(
            "/api/tutor/sessions",
            json={
                "target_node_id": "memory_registration",
                "entry_mode": "normal",
                "client_request_id": str(uuid4()),
            },
        )
        assert locked.status_code == 409
        assert locked.json()["error"]["code"] == "NODE_LOCKED"

        coming_later = client.post(
            "/api/tutor/sessions",
            json={
                "target_node_id": "rdma_cm",
                "entry_mode": "normal",
                "client_request_id": str(uuid4()),
            },
        )
        assert coming_later.status_code == 400
        assert coming_later.json()["error"]["code"] == "COMING_LATER"

        client.post("/api/demo/reset", json={"seed": "golden_path"})
        session = _start(client, "memory_registration", "diagnostic")
        question = session["expected_question"]
        assert question["question_id"] == "mr_q1_copy_check"
        assert "correct_option_ids" not in str(session)
        assert (
            client.get("/api/learner").json()["node_states"]["memory_registration"]["status"]
            == "locked"
        )


def test_active_endpoint_and_mastered_review_mode(tmp_path: Path, curriculum_copy: Path) -> None:
    with TestClient(create_app(_settings(tmp_path, curriculum_copy))) as client:
        assert client.get("/api/tutor/sessions/active").json() is None
        client.post("/api/demo/reset", json={"seed": "golden_path"})
        review = _start(client, "rdma_data_path", "review")
        assert review["mode"] == "review"
        assert review["debug"]["final_action"] == "REVIEW"
        active = client.get("/api/tutor/sessions/active")
        assert active.status_code == 200
        assert active.json()["session_id"] == review["session_id"]


def test_session_response_excludes_secrets_prompts_and_raw_provider_output(
    tmp_path: Path, curriculum_copy: Path
) -> None:
    settings = _settings(tmp_path, curriculum_copy, llm_api_key="do-not-leak-secret")
    with TestClient(create_app(settings)) as client:
        session = _start(client, "virtual_vs_physical_memory", "normal")
        serialized = str(session)
        assert "do-not-leak-secret" not in serialized
        assert "system_prompt" not in serialized
        assert "raw_assessment" not in serialized


def test_turn_conflicts_invalid_option_and_idempotency_do_not_mutate_state(
    tmp_path: Path, curriculum_copy: Path
) -> None:
    with TestClient(create_app(_settings(tmp_path, curriculum_copy))) as client:
        client.post("/api/demo/reset", json={"seed": "golden_path"})
        session = _start(client, "memory_registration", "diagnostic")
        before = _counts(client)

        stale = client.post(
            f"/api/tutor/sessions/{session['session_id']}/turns",
            json={
                "client_turn_id": str(uuid4()),
                "expected_session_version": 99,
                "expected_question_id": "mr_q1_copy_check",
                "kind": "ANSWER",
                "text": "MR 会把内存复制到 HCA。",
                "selected_option_id": None,
            },
        )
        assert stale.status_code == 409
        assert stale.json()["error"]["code"] == "SESSION_VERSION_CONFLICT"

        mismatch = client.post(
            f"/api/tutor/sessions/{session['session_id']}/turns",
            json={
                "client_turn_id": str(uuid4()),
                "expected_session_version": session["version"],
                "expected_question_id": "not-current",
                "kind": "ANSWER",
                "text": "MR 会把内存复制到 HCA。",
                "selected_option_id": None,
            },
        )
        assert mismatch.status_code == 409
        assert mismatch.json()["error"]["code"] == "EXPECTED_QUESTION_MISMATCH"
        assert _counts(client) == before

        turn_id = str(uuid4())
        first = _turn(
            client,
            session,
            text="MR 会把内存复制到 HCA。",
            client_turn_id=turn_id,
        )
        counts = _counts(client)
        repeated = _turn(
            client,
            session,
            text="MR 会把内存复制到 HCA。",
            client_turn_id=turn_id,
        )
        assert repeated == first
        assert _counts(client) == counts

        invalid_option = client.post(
            f"/api/tutor/sessions/{session['session_id']}/turns",
            json={
                "client_turn_id": str(uuid4()),
                "expected_session_version": first["version"],
                "expected_question_id": first["expected_question"]["question_id"],
                "kind": "ANSWER",
                "text": "forged option label",
                "selected_option_id": "not-an-option",
            },
        )
        # The current DMA question is free text, so an option is always invalid.
        assert invalid_option.status_code == 400
        assert invalid_option.json()["error"]["code"] == "INVALID_TURN"


def test_non_answer_turns_preserve_evidence_and_mainline(
    tmp_path: Path, curriculum_copy: Path
) -> None:
    with TestClient(create_app(_settings(tmp_path, curriculum_copy))) as client:
        session = _start(client, "virtual_vs_physical_memory", "normal")
        evidence_before = _counts(client)[2]
        question_id = session["expected_question"]["question_id"]

        side = _turn(client, session, kind="SIDE_QUESTION", text="页表由谁维护？")
        assert side["expected_question"]["question_id"] == question_id
        assert side["debug"]["final_action"] == "ANSWER_SIDE_QUESTION"
        assert all(item["operation"] != "assessor" for item in side["debug"]["llm_metadata"])
        assert _counts(client)[2] == evidence_before

        hinted = _turn(client, side, kind="REQUEST_HINT")
        assert hinted["expected_question"]["question_id"] == question_id
        assert hinted["debug"]["current_assistance_level"] == "light_hint"
        assert _counts(client)[2] == evidence_before

        revealed = _turn(client, hinted, kind="REQUEST_ANSWER")
        assert revealed["expected_question"]["question_id"] != question_id
        assert revealed["debug"]["current_assistance_level"] == "answer_revealed"
        assert _counts(client)[2] == evidence_before

        state_before = client.get("/api/learner").json()["node_states"]
        reported = _turn(client, revealed, kind="SELF_REPORTED_MASTERY")
        state_after = client.get("/api/learner").json()["node_states"]
        assert reported["debug"]["final_action"] == "ASSESS"
        assert state_after == state_before
        assert _counts(client)[2] == evidence_before


def test_assessor_failure_keeps_version_question_and_evidence(
    tmp_path: Path, curriculum_copy: Path
) -> None:
    with TestClient(create_app(_settings(tmp_path, curriculum_copy))) as client:
        client.post("/api/demo/reset", json={"seed": "golden_path"})
        session = _start(client, "memory_registration", "diagnostic")
        before = _counts(client)
        failed = _turn(client, session, text="fixture:schema-invalid-twice")
        assert failed["version"] == session["version"]
        assert failed["expected_question"] == session["expected_question"]
        assert failed["recoverable_error"]["source"] == "assessor"
        assert failed["recoverable_error"]["code"] == "LLM_SCHEMA_VALIDATION_FAILED"
        after = _counts(client)
        assert after[2] == before[2]
        assert after[3] == before[3]


def test_teacher_failure_uses_fallback_without_duplicate_evidence(
    tmp_path: Path, curriculum_copy: Path
) -> None:
    with TestClient(create_app(_settings(tmp_path, curriculum_copy))) as client:
        client.post("/api/demo/reset", json={"seed": "golden_path"})
        session = _start(client, "memory_registration", "diagnostic")
        service = client.app.state.tutor_session_service
        original_teacher = service.teacher

        async def fail_teacher(request: Any) -> TeacherServiceResult:
            return TeacherServiceResult(
                request=request,
                message=original_teacher.fallback_message(request),
                error=LLMError(
                    code=LLMErrorCode.TIMEOUT,
                    message="Teacher 暂时不可用",
                ),
                metadata=[],
            )

        service.teacher.compose = fail_teacher
        turn_id = str(uuid4())
        result = _turn(
            client,
            session,
            text="MR 会把内存复制到 HCA。",
            client_turn_id=turn_id,
        )
        assert result["recoverable_error"] == {
            "code": "LLM_TIMEOUT",
            "message": "Teacher 暂时不可用",
            "source": "teacher",
        }
        assert result["messages"][-1]["interaction_type"] == "recoverable_error"
        counts = _counts(client)
        repeated = _turn(
            client,
            session,
            text="MR 会把内存复制到 HCA。",
            client_turn_id=turn_id,
        )
        assert repeated == result
        assert _counts(client) == counts


def test_session_reload_reset_cascade_and_debug_visibility(
    tmp_path: Path, curriculum_copy: Path
) -> None:
    settings = _settings(tmp_path, curriculum_copy)
    with TestClient(create_app(settings)) as client:
        session = _start(client, "virtual_vs_physical_memory", "normal")
        session_id = session["session_id"]
        question_id = session["expected_question"]["question_id"]
        assert session["debug"]["session_id"] == session_id

    with TestClient(create_app(settings)) as client:
        restored = client.get(f"/api/tutor/sessions/{session_id}")
        assert restored.status_code == 200
        assert restored.json()["expected_question"]["question_id"] == question_id
        assert len(restored.json()["messages"]) == 1
        client.post("/api/demo/reset", json={"seed": "clean"})
        assert client.get(f"/api/tutor/sessions/{session_id}").status_code == 404
        assert _counts(client)[:2] == (0, 0)

    no_debug_settings = _settings(
        tmp_path,
        curriculum_copy,
        database_url=f"sqlite:///{tmp_path / 'no-debug.db'}",
        enable_debug_panel=False,
    )
    with TestClient(create_app(no_debug_settings)) as client:
        session = _start(client, "virtual_vs_physical_memory", "normal")
        assert "debug" not in session


def test_api_golden_path_reaches_mastery_and_ready_next_node(
    tmp_path: Path, curriculum_copy: Path
) -> None:
    with TestClient(create_app(_settings(tmp_path, curriculum_copy))) as client:
        client.post("/api/demo/reset", json={"seed": "golden_path"})
        session = _start(client, "memory_registration", "diagnostic")
        assert session["expected_question"]["question_id"] == "mr_q1_copy_check"

        session = _turn(client, session, text="MR 会把内存复制到 HCA。")
        assert session["current_node"]["node_id"] == "device_dma"
        assert session["return_stack"][0]["node_id"] == "memory_registration"
        assert session["debug"]["final_action"] == "REMEDIATE"

        session = _turn(
            client,
            session,
            text="CPU 负责配置 DMA 工作，DMA 引擎搬运数据，CPU 不执行逐字节复制，完成需要通知。",
        )
        assert session["expected_question"]["question_id"] == "dma_q2_scenario"
        session = _turn(
            client,
            session,
            text="CPU 负责配置和提交，DMA 引擎搬运 payload，CPU 不逐字节复制，完成需要通知或轮询。",
        )
        assert session["current_node"]["node_id"] == "pinned_memory"

        session = _turn(
            client,
            session,
            text="内存页需要保持稳定，映射不能失效，页固定不会复制数据。",
        )
        assert session["expected_question"]["question_id"] == "pin_q2_copy_check"
        assert {item["option_id"] for item in session["expected_question"]["options"]} == {
            "copied",
            "contiguous",
            "stable",
        }
        assert "correct_option_ids" not in str(session["expected_question"])
        before_invalid_option = _counts(client)
        invalid_option = client.post(
            f"/api/tutor/sessions/{session['session_id']}/turns",
            json={
                "client_turn_id": str(uuid4()),
                "expected_session_version": session["version"],
                "expected_question_id": "pin_q2_copy_check",
                "kind": "ANSWER",
                "text": "forged label",
                "selected_option_id": "not-valid",
            },
        )
        assert invalid_option.status_code == 400
        assert invalid_option.json()["error"]["code"] == "INVALID_OPTION_ID"
        assert _counts(client) == before_invalid_option
        session = _turn(client, session, option_id="stable")
        assert session["current_node"]["node_id"] == "memory_registration"
        assert session["expected_question"]["question_id"] == "mr_q2_explain"

        session = _turn(
            client,
            session,
            text=(
                "页面保持稳定，地址映射供 HCA 使用，key 提供权限保护，数据仍在主机内存而不会复制。"
            ),
        )
        assert session["expected_question"]["question_id"] == "mr_q3_transfer"
        final_turn_id = str(uuid4())
        session = _turn(
            client,
            session,
            text="key 与注册范围相关，HCA 会做权限和范围校验，不能任意访问。",
            client_turn_id=final_turn_id,
        )
        assert session["status"] == "completed"
        assert session["current_node"]["node_id"] == "memory_registration"
        assert session["current_node"]["learner_status"] == "mastered"
        assert session["next_ready_node"]["node_id"] == "lkey_rkey_concept"

        counts = _counts(client)
        repeated = _turn(
            client,
            {**session, "expected_question": {"question_id": "mr_q3_transfer"}},
            text="key 与注册范围相关，HCA 会做权限和范围校验，不能任意访问。",
            client_turn_id=final_turn_id,
        )
        assert repeated == session
        assert _counts(client) == counts
