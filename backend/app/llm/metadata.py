from __future__ import annotations

import json
from contextvars import ContextVar
from datetime import UTC, datetime
from hashlib import sha256
from time import perf_counter
from typing import Any
from uuid import uuid4

from backend.app.llm.contracts import (
    LLMCallMetadata,
    LLMErrorCode,
    LLMMode,
    LLMOperation,
)
from backend.app.llm.prompt_loader import PromptTemplate


def stable_hash(value: Any) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(payload.encode("utf-8")).hexdigest()


class MetadataBuffer:
    def __init__(self) -> None:
        self._items: ContextVar[tuple[LLMCallMetadata, ...]] = ContextVar(
            f"llm_metadata_{uuid4().hex}", default=()
        )

    def append(self, item: LLMCallMetadata) -> None:
        self._items.set((*self._items.get(), item))

    def take(self) -> list[LLMCallMetadata]:
        items = list(self._items.get())
        self._items.set(())
        return items


def build_metadata(
    *,
    operation: LLMOperation,
    mode: LLMMode,
    provider: str,
    model: str | None,
    prompt: PromptTemplate,
    attempt_count: int,
    started_at: float,
    request: Any,
    output: Any | None,
    success: bool,
    error_code: LLMErrorCode | None = None,
    provider_request_id: str | None = None,
    usage: Any | None = None,
) -> LLMCallMetadata:
    def usage_value(name: str) -> int | None:
        value = getattr(usage, name, None) if usage is not None else None
        return value if isinstance(value, int) and value >= 0 else None

    return LLMCallMetadata(
        call_id=f"llmcall_{uuid4().hex}",
        operation=operation,
        mode=mode,
        provider=provider,
        model=model or None,
        prompt_version=prompt.version,
        prompt_hash=prompt.sha256,
        attempt_count=attempt_count,
        latency_ms=max(0, round((perf_counter() - started_at) * 1000)),
        provider_request_id=provider_request_id,
        success=success,
        error_code=error_code,
        input_hash=stable_hash(request),
        output_hash=stable_hash(output) if output is not None else None,
        input_tokens=usage_value("input_tokens"),
        output_tokens=usage_value("output_tokens"),
        total_tokens=usage_value("total_tokens"),
        created_at=datetime.now(UTC),
    )
