from sqlalchemy.orm import Session, sessionmaker

from backend.app.core.config import Settings
from backend.app.llm.contracts import LLMMode, LLMStatus
from backend.app.llm.repository import LLMCallRepository


class LLMStatusService:
    def __init__(self, settings: Settings, session_factory: sessionmaker[Session]) -> None:
        self.settings = settings
        self.session_factory = session_factory

    def get(self) -> LLMStatus:
        assessor_configured = bool(self.settings.llm_assessor_model)
        teacher_configured = bool(self.settings.llm_teacher_model)
        key_configured = bool(self.settings.llm_api_key)
        with self.session_factory() as db:
            last_error = LLMCallRepository(db).last_error_code()
        return LLMStatus(
            mode=LLMMode(self.settings.llm_mode),
            provider=self.settings.llm_provider,
            assessor_model_configured=assessor_configured,
            teacher_model_configured=teacher_configured,
            api_key_configured=key_configured,
            live_ready=(
                self.settings.llm_mode == "live"
                and assessor_configured
                and teacher_configured
                and key_configured
            ),
            last_error_code=last_error,
        )
