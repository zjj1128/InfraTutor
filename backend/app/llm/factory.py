from backend.app.core.config import Settings
from backend.app.llm.gateway import LLMGateway
from backend.app.llm.mock_provider import MockLLMGateway
from backend.app.llm.openai_provider import OpenAILiveGateway
from backend.app.llm.prompt_loader import PromptLoader


def create_llm_gateway(settings: Settings, prompt_loader: PromptLoader) -> LLMGateway:
    if settings.llm_mode == "mock":
        return MockLLMGateway(prompt_loader)
    return OpenAILiveGateway(settings, prompt_loader)
