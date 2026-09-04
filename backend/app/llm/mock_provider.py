from __future__ import annotations

from time import perf_counter

from backend.app.llm.contracts import (
    AssessmentRequest,
    AssessmentResult,
    ExpectedResponseType,
    LLMCallMetadata,
    LLMErrorCode,
    LLMMode,
    LLMOperation,
    TutorInteractionType,
    TutorMessageRequest,
    TutorMessageResult,
)
from backend.app.llm.errors import LLMGatewayError
from backend.app.llm.metadata import MetadataBuffer, build_metadata
from backend.app.llm.prompt_loader import PromptLoader, PromptTemplate
from backend.app.tutor.domain import RecommendedAction, RubricResult, Understanding


class MockLLMGateway:
    """A deterministic fixture provider, deliberately not a general language model."""

    def __init__(self, prompt_loader: PromptLoader) -> None:
        self.prompt_loader = prompt_loader
        self._metadata = MetadataBuffer()

    def take_metadata(self) -> list[LLMCallMetadata]:
        return self._metadata.take()

    async def aclose(self) -> None:
        return None

    async def assess_answer(self, request: AssessmentRequest) -> AssessmentResult:
        started_at = perf_counter()
        prompt = self.prompt_loader.assessor()
        attempt = 2 if request.repair_context else 1
        normalized = " ".join(request.learner_answer.casefold().split())

        fixture_error = self._assessment_fixture_error(normalized, request)
        if fixture_error is not None:
            self._record_failure(
                LLMOperation.ASSESSOR,
                prompt,
                request,
                started_at,
                attempt,
                fixture_error.detail.code,
            )
            raise fixture_error

        if "忽略" in normalized and "mastered" in normalized:
            result = self._ambiguous(request)
        elif (
            request.question.question_id == "mr_q1_copy_check"
            and all(token in normalized for token in ("复制", "hca"))
            and "不会" not in normalized
            and "不复制" not in normalized
        ):
            result = self._incorrect(
                request,
                misconception_id="mr_copies_memory_to_hca",
                missing_concept_ids=["device_dma", "pinned_memory"],
                evidence_span=self._matching_span(request.learner_answer, "复制", "HCA"),
            )
        elif (
            request.question.node_id == "device_dma"
            and (
                ("cpu" in normalized and "memcpy" in normalized)
                or ("cpu" in normalized and "逐字节" in normalized and "搬运" in normalized)
            )
            and "不" not in normalized
        ):
            result = self._incorrect(
                request,
                misconception_id="dma_is_cpu_memcpy",
                missing_concept_ids=["device_dma"],
                evidence_span=request.learner_answer[:400],
            )
        elif self._is_known_correct(request, normalized):
            result = self._correct(request)
        else:
            result = self._ambiguous(request)

        self._metadata.append(
            build_metadata(
                operation=LLMOperation.ASSESSOR,
                mode=LLMMode.MOCK,
                provider="mock",
                model="mock-deterministic-v1",
                prompt=prompt,
                attempt_count=attempt,
                started_at=started_at,
                request=request,
                output=result,
                success=True,
            )
        )
        return result

    async def compose_tutor_message(self, request: TutorMessageRequest) -> TutorMessageResult:
        started_at = perf_counter()
        prompt = self.prompt_loader.teacher()
        attempt = 2 if request.repair_context else 1
        fixture = request.directive.preferred_method or ""
        if "fixture:teacher-invalid-twice" in fixture or (
            "fixture:teacher-invalid-first" in fixture and request.repair_context is None
        ):
            error = LLMGatewayError(
                LLMErrorCode.SCHEMA_VALIDATION_FAILED,
                "Mock Teacher fixture 返回了非法 schema",
                validation_errors=["question_id: field required"],
                previous_output={"student_message": "invalid"},
            )
            self._record_failure(
                LLMOperation.TEACHER, prompt, request, started_at, attempt, error.detail.code
            )
            raise error

        question = request.question_to_ask
        interaction = self._interaction_for_action(request)
        if question is None:
            message = self._prefix(request)
            response_type = ExpectedResponseType.NONE
            question_id = None
        else:
            message = f"{self._prefix(request)}{question.prompt}"
            response_type = ExpectedResponseType(question.question_type.value)
            question_id = question.question_id
        message = message[: request.directive.max_length_chars]
        result = TutorMessageResult(
            student_message=message,
            interaction_type=interaction,
            expected_response_type=response_type,
            question_id=question_id,
            quick_replies=[],
        )
        self._metadata.append(
            build_metadata(
                operation=LLMOperation.TEACHER,
                mode=LLMMode.MOCK,
                provider="mock",
                model="mock-deterministic-v1",
                prompt=prompt,
                attempt_count=attempt,
                started_at=started_at,
                request=request,
                output=result,
                success=True,
            )
        )
        return result

    def _assessment_fixture_error(
        self, normalized: str, request: AssessmentRequest
    ) -> LLMGatewayError | None:
        if "fixture:refusal" in normalized:
            return LLMGatewayError(LLMErrorCode.REFUSED, "Mock provider refusal")
        if "fixture:timeout" in normalized:
            return LLMGatewayError(LLMErrorCode.TIMEOUT, "Mock provider timeout")
        invalid_twice = "fixture:schema-invalid-twice" in normalized
        invalid_first = "fixture:schema-invalid-first-then-valid" in normalized
        if invalid_twice or (invalid_first and request.repair_context is None):
            return LLMGatewayError(
                LLMErrorCode.SCHEMA_VALIDATION_FAILED,
                "Mock Assessor fixture 返回了非法 schema",
                validation_errors=["rubric_results: field required"],
                previous_output={"question_id": request.question.question_id},
            )
        return None

    @staticmethod
    def _matching_span(answer: str, *tokens: str) -> str:
        lowered = answer.casefold()
        positions = [lowered.find(token.casefold()) for token in tokens]
        present = [position for position in positions if position >= 0]
        if not present:
            return ""
        start = min(present)
        return answer[start : start + 120]

    @staticmethod
    def _correct(request: AssessmentRequest) -> AssessmentResult:
        return AssessmentResult(
            question_id=request.question.question_id,
            node_id=request.question.node_id,
            understanding=Understanding.CORRECT,
            score=1.0,
            rubric_results=[
                RubricResult(criterion_id=item.criterion_id, result="met", evidence_span="")
                for item in request.question.rubric_criteria
            ],
            misconception_ids=[],
            missing_concept_ids=[],
            answer_is_ambiguous=False,
            feedback_points=["回答覆盖了本题 rubric"],
            recommended_action=RecommendedAction.ADVANCE_CANDIDATE,
            recommended_target_node_id=None,
        )

    @staticmethod
    def _incorrect(
        request: AssessmentRequest,
        *,
        misconception_id: str,
        missing_concept_ids: list[str],
        evidence_span: str,
    ) -> AssessmentResult:
        return AssessmentResult(
            question_id=request.question.question_id,
            node_id=request.question.node_id,
            understanding=Understanding.INCORRECT,
            score=0.0,
            rubric_results=[
                RubricResult(
                    criterion_id=item.criterion_id,
                    result="not_met",
                    evidence_span=evidence_span,
                )
                for item in request.question.rubric_criteria
            ],
            misconception_ids=[misconception_id],
            missing_concept_ids=missing_concept_ids,
            answer_is_ambiguous=False,
            feedback_points=["回答暴露了课程定义的关键误解"],
            recommended_action=RecommendedAction.REMEDIATE,
            recommended_target_node_id=missing_concept_ids[0],
        )

    @staticmethod
    def _ambiguous(request: AssessmentRequest) -> AssessmentResult:
        return AssessmentResult(
            question_id=request.question.question_id,
            node_id=request.question.node_id,
            understanding=Understanding.UNCERTAIN,
            score=0.5,
            rubric_results=[
                RubricResult(
                    criterion_id=item.criterion_id,
                    result="uncertain",
                    evidence_span="",
                )
                for item in request.question.rubric_criteria
            ],
            misconception_ids=[],
            missing_concept_ids=[],
            answer_is_ambiguous=True,
            feedback_points=["回答信息不足或与问题不匹配"],
            recommended_action=RecommendedAction.ASK_FOLLOWUP,
            recommended_target_node_id=None,
        )

    @staticmethod
    def _is_known_correct(request: AssessmentRequest, normalized: str) -> bool:
        if "fixture:correct" in normalized:
            return True
        if request.repair_context is not None and "schema-invalid-first-then-valid" in normalized:
            return True
        if request.question.question_id == "pin_q2_copy_check":
            return (
                normalized == "stable"
                or all(token in normalized for token in ("稳定", "不", "复制"))
                or all(token in normalized for token in ("稳定", "原内存"))
            )
        node = request.question.node_id
        rules = {
            "device_dma": ("cpu", "dma", "搬运", "完成"),
            "pinned_memory": ("页", "稳定", "映射", "不", "复制"),
            "memory_registration": ("内存", "注册", "key"),
        }
        tokens = rules.get(node)
        if tokens is None:
            return False
        if node == "memory_registration" and request.question.question_id == "mr_q2_explain":
            tokens = ("稳定", "映射", "保护", "主机内存", "不")
        if node == "memory_registration" and request.question.question_id == "mr_q3_transfer":
            tokens = ("范围", "key", "校验")
        return all(token in normalized for token in tokens)

    @staticmethod
    def _interaction_for_action(request: TutorMessageRequest) -> TutorInteractionType:
        return {
            "ORIENT": TutorInteractionType.ORIENTATION,
            "TEACH": TutorInteractionType.EXPLANATION,
            "ASK": TutorInteractionType.GUIDED_QUESTION,
            "ASSESS": TutorInteractionType.FORMAL_ASSESSMENT,
            "HINT": TutorInteractionType.HINT,
            "RETRY": TutorInteractionType.GUIDED_QUESTION,
            "REMEDIATE": TutorInteractionType.REMEDIATION,
            "REVIEW": TutorInteractionType.REVIEW,
            "ADVANCE": TutorInteractionType.TRANSITION,
            "ANSWER_SIDE_QUESTION": TutorInteractionType.SIDE_ANSWER,
        }[request.action.value]

    @staticmethod
    def _prefix(request: TutorMessageRequest) -> str:
        if request.action.value == "REMEDIATE":
            return f"我们先回到 {request.current_node.title} 补齐关键前置。"
        if request.action.value == "HINT":
            return "给你一个提示：先区分控制工作和 payload 搬运。"
        if request.action.value == "ANSWER_SIDE_QUESTION":
            return "这个问题与当前主线相关；回答后我们继续原问题。"
        if request.action.value == "TEACH":
            fact = request.current_node.canonical_facts[0]
            return f"直接讲解：{fact} 接下来换一道题重新确认。"
        return "我们继续当前学习目标。"

    def _record_failure(
        self,
        operation: LLMOperation,
        prompt: PromptTemplate,
        request: AssessmentRequest | TutorMessageRequest,
        started_at: float,
        attempt: int,
        error_code: LLMErrorCode,
    ) -> None:
        self._metadata.append(
            build_metadata(
                operation=operation,
                mode=LLMMode.MOCK,
                provider="mock",
                model="mock-deterministic-v1",
                prompt=prompt,
                attempt_count=attempt,
                started_at=started_at,
                request=request,
                output=None,
                success=False,
                error_code=error_code,
            )
        )
