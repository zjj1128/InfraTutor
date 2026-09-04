from __future__ import annotations

from typing import Any

from backend.app.llm.contracts import LLMError, LLMErrorCode


class LLMGatewayError(RuntimeError):
    def __init__(
        self,
        code: LLMErrorCode,
        message: str,
        *,
        recoverable: bool = True,
        validation_errors: list[str] | None = None,
        previous_output: dict[str, Any] | str | None = None,
    ) -> None:
        super().__init__(message)
        self.detail = LLMError(
            code=code,
            message=message,
            recoverable=recoverable,
            validation_errors=validation_errors or [],
        )
        self.previous_output = previous_output if previous_output is not None else ""


class SemanticValidationError(ValueError):
    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors
