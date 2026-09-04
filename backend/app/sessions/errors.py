from enum import StrEnum
from typing import Any


class SessionErrorCode(StrEnum):
    SESSION_NOT_FOUND = "SESSION_NOT_FOUND"
    ACTIVE_SESSION_EXISTS = "ACTIVE_SESSION_EXISTS"
    SESSION_VERSION_CONFLICT = "SESSION_VERSION_CONFLICT"
    EXPECTED_QUESTION_MISMATCH = "EXPECTED_QUESTION_MISMATCH"
    SESSION_NOT_ACTIVE = "SESSION_NOT_ACTIVE"
    NODE_LOCKED = "NODE_LOCKED"
    DIAGNOSTIC_PROBE_NOT_ALLOWED = "DIAGNOSTIC_PROBE_NOT_ALLOWED"
    COMING_LATER = "COMING_LATER"
    INVALID_ENTRY_MODE = "INVALID_ENTRY_MODE"
    INVALID_OPTION_ID = "INVALID_OPTION_ID"
    INVALID_TURN = "INVALID_TURN"
    TURN_IN_PROGRESS = "TURN_IN_PROGRESS"


class TutorSessionError(ValueError):
    def __init__(
        self,
        code: SessionErrorCode,
        message: str,
        *,
        status_code: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
