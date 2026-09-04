from __future__ import annotations

from time import perf_counter
from typing import Any, TypeVar

import openai
from openai import AsyncOpenAI
from pydantic import BaseModel, ValidationError

from backend.app.core.config import Settings
from backend.app.llm.contracts import (
    AssessmentRequest,
    AssessmentResult,
    LLMCallMetadata,
    LLMErrorCode,
    LLMMode,
    LLMOperation,
    TutorMessageRequest,
    TutorMessageResult,
)
from backend.app.llm.errors import LLMGatewayError
from backend.app.llm.metadata import MetadataBuffer, build_metadata
from backend.app.llm.prompt_loader import PromptLoader, PromptTemplate

OutputT = TypeVar("OutputT", bound=BaseModel)


class OpenAILiveGateway:
    def __init__(
        self,
        settings: Settings,
        prompt_loader: PromptLoader,
        *,
        client: Any | None = None,
    ) -> None:
        self.settings = settings
        self.prompt_loader = prompt_loader
        self._client = client
        self._metadata = MetadataBuffer()

    def take_metadata(self) -> list[LLMCallMetadata]:
        return self._metadata.take()

    async def aclose(self) -> None:
        client = self._client
        if client is not None and hasattr(client, "close"):
            await client.close()

    async def assess_answer(self, request: AssessmentRequest) -> AssessmentResult:
        return await self._call(
            operation=LLMOperation.ASSESSOR,
            request=request,
            prompt=self.prompt_loader.assessor(),
            model=self.settings.llm_assessor_model,
            output_type=AssessmentResult,
        )

    async def compose_tutor_message(self, request: TutorMessageRequest) -> TutorMessageResult:
        return await self._call(
            operation=LLMOperation.TEACHER,
            request=request,
            prompt=self.prompt_loader.teacher(),
            model=self.settings.llm_teacher_model,
            output_type=TutorMessageResult,
        )

    async def _call(
        self,
        *,
        operation: LLMOperation,
        request: AssessmentRequest | TutorMessageRequest,
        prompt: PromptTemplate,
        model: str,
        output_type: type[OutputT],
    ) -> OutputT:
        started_at = perf_counter()
        attempt = 2 if request.repair_context else 1
        if not self.settings.llm_api_key or not model:
            error = LLMGatewayError(
                LLMErrorCode.NOT_CONFIGURED,
                f"Live {operation.value} 未配置 API Key 或模型 ID",
            )
            self._record_failure(operation, request, prompt, model, attempt, started_at, error)
            raise error

        if self._client is None:
            self._client = self._create_client()
        client = self._client
        response: Any | None = None
        try:
            response = await client.responses.parse(
                model=model,
                instructions=prompt.content,
                input=[
                    {
                        "role": "user",
                        "content": request.model_dump_json(exclude_none=False),
                    }
                ],
                text_format=output_type,
                store=False,
            )
            request_id = getattr(response, "_request_id", None)
            if getattr(response, "status", None) == "incomplete":
                raise LLMGatewayError(
                    LLMErrorCode.INCOMPLETE_OUTPUT,
                    "OpenAI Responses API 返回 incomplete output",
                )
            if self._has_refusal(response):
                raise LLMGatewayError(LLMErrorCode.REFUSED, "OpenAI 拒绝生成本次输出")
            parsed = getattr(response, "output_parsed", None)
            if parsed is None:
                raise LLMGatewayError(
                    LLMErrorCode.INCOMPLETE_OUTPUT,
                    "OpenAI response.output_parsed 为空",
                )
            if not isinstance(parsed, output_type):
                parsed = output_type.model_validate(parsed)
        except LLMGatewayError as exc:
            self._record_failure(
                operation,
                request,
                prompt,
                model,
                attempt,
                started_at,
                exc,
                provider_request_id=getattr(response, "_request_id", None),
            )
            raise
        except ValidationError as exc:
            error = LLMGatewayError(
                LLMErrorCode.SCHEMA_VALIDATION_FAILED,
                "OpenAI Structured Output 未通过 Pydantic 校验",
                validation_errors=[item["msg"] for item in exc.errors()[:32]],
                previous_output=getattr(response, "output_text", ""),
            )
            self._record_failure(operation, request, prompt, model, attempt, started_at, error)
            raise error from exc
        except Exception as exc:
            error = self._translate_provider_error(exc)
            self._record_failure(
                operation,
                request,
                prompt,
                model,
                attempt,
                started_at,
                error,
                provider_request_id=getattr(exc, "request_id", None),
            )
            raise error from exc

        self._metadata.append(
            build_metadata(
                operation=operation,
                mode=LLMMode.LIVE,
                provider="openai",
                model=model,
                prompt=prompt,
                attempt_count=attempt,
                started_at=started_at,
                request=request,
                output=parsed,
                success=True,
                provider_request_id=request_id,
                usage=getattr(response, "usage", None),
            )
        )
        return parsed

    def _create_client(self) -> AsyncOpenAI:
        options: dict[str, Any] = {
            "api_key": self.settings.llm_api_key,
            "timeout": self.settings.llm_timeout_seconds,
            "max_retries": self.settings.llm_transport_max_retries,
        }
        if self.settings.llm_base_url:
            options["base_url"] = self.settings.llm_base_url
        return AsyncOpenAI(**options)

    def _translate_provider_error(self, exc: Exception) -> LLMGatewayError:
        if isinstance(exc, openai.APITimeoutError):
            code = LLMErrorCode.TIMEOUT
        elif isinstance(exc, openai.LengthFinishReasonError):
            code = LLMErrorCode.INCOMPLETE_OUTPUT
        elif isinstance(exc, openai.ContentFilterFinishReasonError):
            code = LLMErrorCode.REFUSED
        elif isinstance(exc, openai.APIResponseValidationError):
            code = LLMErrorCode.SCHEMA_VALIDATION_FAILED
        elif isinstance(exc, openai.RateLimitError):
            code = LLMErrorCode.RATE_LIMITED
        elif isinstance(exc, (openai.AuthenticationError, openai.PermissionDeniedError)):
            code = LLMErrorCode.AUTH_FAILED
        elif isinstance(exc, openai.APIConnectionError):
            code = LLMErrorCode.PROVIDER_UNAVAILABLE
        elif isinstance(exc, openai.APIStatusError):
            status = exc.status_code
            if status == 408:
                code = LLMErrorCode.TIMEOUT
            elif status in {400, 404, 405, 422}:
                code = LLMErrorCode.INCOMPATIBLE_ENDPOINT
            else:
                code = LLMErrorCode.PROVIDER_UNAVAILABLE
        else:
            code = LLMErrorCode.PROVIDER_UNAVAILABLE
        return LLMGatewayError(code, f"OpenAI provider 调用失败（{code.value}）")

    @staticmethod
    def _has_refusal(response: Any) -> bool:
        for output in getattr(response, "output", []) or []:
            for content in getattr(output, "content", []) or []:
                if getattr(content, "type", None) == "refusal":
                    return True
        return False

    def _record_failure(
        self,
        operation: LLMOperation,
        request: AssessmentRequest | TutorMessageRequest,
        prompt: PromptTemplate,
        model: str,
        attempt: int,
        started_at: float,
        error: LLMGatewayError,
        *,
        provider_request_id: str | None = None,
    ) -> None:
        self._metadata.append(
            build_metadata(
                operation=operation,
                mode=LLMMode.LIVE,
                provider="openai",
                model=model or None,
                prompt=prompt,
                attempt_count=attempt,
                started_at=started_at,
                request=request,
                output=None,
                success=False,
                error_code=error.detail.code,
                provider_request_id=provider_request_id,
            )
        )
