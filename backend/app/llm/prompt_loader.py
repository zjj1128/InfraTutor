from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from backend.app.core.config import PROJECT_ROOT


class PromptLoadError(RuntimeError):
    pass


@dataclass(frozen=True)
class PromptTemplate:
    name: str
    content: str
    version: str
    sha256: str


class PromptLoader:
    def __init__(self, prompt_dir: Path = PROJECT_ROOT / "prompts") -> None:
        self.prompt_dir = prompt_dir
        self._cache: dict[str, PromptTemplate] = {}

    def load_all(self) -> None:
        self.assessor()
        self.teacher()

    def assessor(self) -> PromptTemplate:
        return self._load("assessor", "assessor_system.md")

    def teacher(self) -> PromptTemplate:
        return self._load("teacher", "teacher_system.md")

    def _load(self, name: str, filename: str) -> PromptTemplate:
        if name in self._cache:
            return self._cache[name]
        path = self.prompt_dir / filename
        try:
            content = path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise PromptLoadError(f"无法加载 {name} system prompt: {path}: {exc}") from exc
        if not content:
            raise PromptLoadError(f"{name} system prompt 为空: {path}")
        digest = sha256(content.encode("utf-8")).hexdigest()
        template = PromptTemplate(
            name=name,
            content=content,
            version=f"{name}-{digest[:12]}",
            sha256=digest,
        )
        self._cache[name] = template
        return template
