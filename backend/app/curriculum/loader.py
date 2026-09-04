from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

import yaml
from pydantic import BaseModel, ValidationError

from backend.app.curriculum.models import AssessmentSet, PilotModule, Roadmap
from backend.app.curriculum.validator import validate_curriculum

ModelT = TypeVar("ModelT", bound=BaseModel)


class CurriculumLoadError(RuntimeError):
    pass


@dataclass(frozen=True)
class CurriculumCatalog:
    roadmap: Roadmap
    pilot: PilotModule
    assessment_set: AssessmentSet


def _load_yaml(path: Path, model_type: type[ModelT]) -> ModelT:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise CurriculumLoadError(f"无法读取课程文件 {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise CurriculumLoadError(f"课程 YAML 语法错误 {path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise CurriculumLoadError(f"课程文件顶层必须是对象: {path}")

    try:
        return model_type.model_validate(raw)
    except ValidationError as exc:
        raise CurriculumLoadError(f"课程文件结构无效 {path}:\n{exc}") from exc


def load_curriculum(curriculum_dir: Path) -> CurriculumCatalog:
    roadmap = _load_yaml(curriculum_dir / "roadmap.yaml", Roadmap)
    pilot = _load_yaml(
        curriculum_dir / "v0_1_rdma_memory_registration.yaml",
        PilotModule,
    )
    assessment_set = _load_yaml(
        curriculum_dir / "v0_1_assessments.yaml",
        AssessmentSet,
    )
    validate_curriculum(roadmap, pilot, assessment_set)
    return CurriculumCatalog(
        roadmap=roadmap,
        pilot=pilot,
        assessment_set=assessment_set,
    )
