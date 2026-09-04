from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.llm.contracts import LLMCallMetadata, LLMErrorCode
from backend.app.llm.models import LLMCallRecord


class LLMCallRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(
        self,
        metadata: LLMCallMetadata,
        *,
        session_id: str | None,
        client_turn_id: str | None,
    ) -> None:
        self.session.add(
            LLMCallRecord(
                id=metadata.call_id,
                session_id=session_id,
                client_turn_id=client_turn_id,
                operation=metadata.operation.value,
                mode=metadata.mode.value,
                provider=metadata.provider,
                model=metadata.model,
                prompt_version=metadata.prompt_version,
                prompt_hash=metadata.prompt_hash,
                attempt_count=metadata.attempt_count,
                latency_ms=metadata.latency_ms,
                provider_request_id=metadata.provider_request_id,
                success=metadata.success,
                error_code=metadata.error_code.value if metadata.error_code else None,
                input_hash=metadata.input_hash,
                output_hash=metadata.output_hash,
                input_tokens=metadata.input_tokens,
                output_tokens=metadata.output_tokens,
                total_tokens=metadata.total_tokens,
                created_at=metadata.created_at,
            )
        )

    def last_error_code(self) -> LLMErrorCode | None:
        statement = (
            select(LLMCallRecord.error_code)
            .where(LLMCallRecord.error_code.is_not(None))
            .order_by(LLMCallRecord.created_at.desc(), LLMCallRecord.id.desc())
            .limit(1)
        )
        value = self.session.scalar(statement)
        return LLMErrorCode(value) if value else None
