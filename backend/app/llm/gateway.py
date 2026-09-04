from __future__ import annotations

from typing import Protocol, runtime_checkable

from backend.app.llm.contracts import (
    AssessmentRequest,
    AssessmentResult,
    LLMCallMetadata,
    TutorMessageRequest,
    TutorMessageResult,
)


@runtime_checkable
class LLMGateway(Protocol):
    async def assess_answer(self, request: AssessmentRequest) -> AssessmentResult: ...

    async def compose_tutor_message(self, request: TutorMessageRequest) -> TutorMessageResult: ...

    def take_metadata(self) -> list[LLMCallMetadata]: ...

    async def aclose(self) -> None: ...
