import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest

from backend.app.curriculum.loader import CurriculumCatalog, load_curriculum
from backend.app.db.session import (
    create_database_engine,
    create_session_factory,
    initialize_database,
)
from backend.app.learner.service import LearnerStateService

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def curriculum_copy(tmp_path: Path) -> Iterator[Path]:
    destination = tmp_path / "curriculum"
    shutil.copytree(PROJECT_ROOT / "curriculum", destination)
    yield destination


@pytest.fixture
def curriculum_catalog(curriculum_copy: Path) -> CurriculumCatalog:
    return load_curriculum(curriculum_copy)


@pytest.fixture
def learner_service(
    tmp_path: Path, curriculum_catalog: CurriculumCatalog
) -> Iterator[LearnerStateService]:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'learner-state.db'}")
    initialize_database(engine)
    service = LearnerStateService(curriculum_catalog, create_session_factory(engine))
    service.ensure_default_learner()
    yield service
    engine.dispose()
