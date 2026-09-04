from __future__ import annotations

from dataclasses import dataclass

from backend.app.core.config import Settings
from backend.app.llm.builders import AssessmentRequestBuilder
from backend.app.llm.contracts import (
    AssessmentRequest,
    AssessmentResult,
    ExpectedResponseType,
    LLMCallMetadata,
    LLMError,
    LLMErrorCode,
    RepairContext,
    TutorInteractionType,
    TutorMessageRequest,
    TutorMessageResult,
)
from backend.app.llm.errors import LLMGatewayError, SemanticValidationError
from backend.app.llm.gateway import LLMGateway
from backend.app.llm.validation import (
    AssessmentSemanticValidator,
    CanonicalAssessment,
    TeacherSemanticValidator,
)
from backend.app.tutor.domain import LearningSessionView


@dataclass(frozen=True)
class AssessmentServiceResult:
    request: AssessmentRequest
    raw: AssessmentResult | None
    canonical: AssessmentResult | None
    warnings: list[str]
    error: LLMError | None
    metadata: list[LLMCallMetadata]


@dataclass(frozen=True)
class TeacherServiceResult:
    request: TutorMessageRequest
    message: TutorMessageResult
    error: LLMError | None
    metadata: list[LLMCallMetadata]


class AssessorService:
    def __init__(
        self,
        settings: Settings,
        gateway: LLMGateway,
        builder: AssessmentRequestBuilder,
        validator: AssessmentSemanticValidator,
    ) -> None:
        self.settings = settings
        self.gateway = gateway
        self.builder = builder
        self.validator = validator

    async def assess(
        self, session: LearningSessionView, learner_answer: str
    ) -> AssessmentServiceResult:
        request = self.builder.build(session, learner_answer)
        current_request = request
        metadata: list[LLMCallMetadata] = []
        last_error: LLMError | None = None
        for attempt in range(self.settings.llm_repair_retries + 1):
            try:
                raw = await self.gateway.assess_answer(current_request)
                metadata.extend(self.gateway.take_metadata())
                validated = self.validator.validate_and_canonicalize(request, raw)
                return self._success(request, validated, metadata)
            except LLMGatewayError as exc:
                metadata.extend(self.gateway.take_metadata())
                last_error = exc.detail
                if not self._repairable(exc.detail.code) or (
                    attempt >= self.settings.llm_repair_retries
                ):
                    break
                current_request = request.model_copy(
                    update={
                        "repair_context": self._repair_context(
                            exc.previous_output, exc.detail.validation_errors, request
                        )
                    },
                    deep=True,
                )
            except SemanticValidationError as exc:
                self._mark_last_metadata_failed(metadata, LLMErrorCode.SEMANTIC_VALIDATION_FAILED)
                last_error = LLMError(
                    code=LLMErrorCode.SEMANTIC_VALIDATION_FAILED,
                    message="Assessor output 未通过课程语义校验",
                    validation_errors=exc.errors,
                )
                if attempt >= self.settings.llm_repair_retries:
                    break
                current_request = request.model_copy(
                    update={
                        "repair_context": self._repair_context(
                            raw.model_dump(mode="json"), exc.errors, request
                        )
                    },
                    deep=True,
                )
        return AssessmentServiceResult(
            request=request,
            raw=None,
            canonical=None,
            warnings=[],
            error=last_error
            or LLMError(
                code=LLMErrorCode.SCHEMA_VALIDATION_FAILED,
                message="Assessor output 校验失败",
            ),
            metadata=metadata,
        )

    @staticmethod
    def _success(
        request: AssessmentRequest,
        result: CanonicalAssessment,
        metadata: list[LLMCallMetadata],
    ) -> AssessmentServiceResult:
        return AssessmentServiceResult(
            request=request,
            raw=result.raw,
            canonical=result.result,
            warnings=result.warnings,
            error=None,
            metadata=metadata,
        )

    @staticmethod
    def _repairable(code: LLMErrorCode) -> bool:
        return code in {
            LLMErrorCode.SCHEMA_VALIDATION_FAILED,
            LLMErrorCode.SEMANTIC_VALIDATION_FAILED,
        }

    @staticmethod
    def _mark_last_metadata_failed(metadata: list[LLMCallMetadata], code: LLMErrorCode) -> None:
        if metadata:
            metadata[-1] = metadata[-1].model_copy(update={"success": False, "error_code": code})

    @staticmethod
    def _repair_context(
        previous_output: dict[str, object] | str,
        errors: list[str],
        request: AssessmentRequest,
    ) -> RepairContext:
        return RepairContext(
            previous_output=previous_output,
            validation_errors=errors or ["Structured output validation failed"],
            output_schema=AssessmentResult.model_json_schema(),
            allowed_ids={
                "question_ids": [request.question.question_id],
                "node_ids": [request.question.node_id],
                "criterion_ids": [item.criterion_id for item in request.question.rubric_criteria],
                "misconception_ids": request.allowed_misconception_ids,
                "missing_concept_ids": request.allowed_missing_concept_ids,
            },
        )


class TeacherService:
    def __init__(self, settings: Settings, gateway: LLMGateway) -> None:
        self.settings = settings
        self.gateway = gateway
        self.validator = TeacherSemanticValidator()

    async def compose(self, request: TutorMessageRequest) -> TeacherServiceResult:
        current_request = request
        metadata: list[LLMCallMetadata] = []
        last_error: LLMError | None = None
        for attempt in range(self.settings.llm_repair_retries + 1):
            try:
                message = await self.gateway.compose_tutor_message(current_request)
                metadata.extend(self.gateway.take_metadata())
                self.validator.validate(request, message)
                return TeacherServiceResult(request, message, None, metadata)
            except LLMGatewayError as exc:
                metadata.extend(self.gateway.take_metadata())
                last_error = exc.detail
                if not AssessorService._repairable(exc.detail.code) or (
                    attempt >= self.settings.llm_repair_retries
                ):
                    break
                current_request = self._with_repair(
                    request, exc.previous_output, exc.detail.validation_errors
                )
            except SemanticValidationError as exc:
                AssessorService._mark_last_metadata_failed(
                    metadata, LLMErrorCode.SEMANTIC_VALIDATION_FAILED
                )
                last_error = LLMError(
                    code=LLMErrorCode.SEMANTIC_VALIDATION_FAILED,
                    message="Teacher output 未通过教学语义校验",
                    validation_errors=exc.errors,
                )
                if attempt >= self.settings.llm_repair_retries:
                    break
                current_request = self._with_repair(
                    request, message.model_dump(mode="json"), exc.errors
                )
        return TeacherServiceResult(
            request=request,
            message=self.fallback_message(request),
            error=last_error
            or LLMError(
                code=LLMErrorCode.SCHEMA_VALIDATION_FAILED,
                message="Teacher output 校验失败",
            ),
            metadata=metadata,
        )

    @staticmethod
    def fallback_message(request: TutorMessageRequest) -> TutorMessageResult:
        question = request.question_to_ask
        if question is None:
            text = "本轮回复生成失败，请重试。"
            response_type = ExpectedResponseType.NONE
            question_id = None
        else:
            text = f"本轮回复生成失败，我们继续当前问题：{question.prompt}"
            response_type = ExpectedResponseType(question.question_type.value)
            question_id = question.question_id
        return TutorMessageResult(
            student_message=text[: request.directive.max_length_chars],
            interaction_type=TutorInteractionType.RECOVERABLE_ERROR,
            expected_response_type=response_type,
            question_id=question_id,
            quick_replies=[],
        )

    @staticmethod
    def _with_repair(
        request: TutorMessageRequest,
        previous_output: dict[str, object] | str,
        errors: list[str],
    ) -> TutorMessageRequest:
        question_ids = (
            [request.question_to_ask.question_id] if request.question_to_ask is not None else []
        )
        return request.model_copy(
            update={
                "repair_context": RepairContext(
                    previous_output=previous_output,
                    validation_errors=errors or ["Structured output validation failed"],
                    output_schema=TutorMessageResult.model_json_schema(),
                    allowed_ids={
                        "question_ids": question_ids,
                        "target_node_ids": [request.course_target_node.node_id],
                        "current_node_ids": [request.current_node.node_id],
                    },
                )
            },
            deep=True,
        )
