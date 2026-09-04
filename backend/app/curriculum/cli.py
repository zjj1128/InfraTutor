from backend.app.core.config import get_settings
from backend.app.curriculum.loader import CurriculumLoadError, load_curriculum
from backend.app.curriculum.validator import CurriculumValidationError


def main() -> int:
    settings = get_settings()
    try:
        catalog = load_curriculum(settings.curriculum_dir)
    except (CurriculumLoadError, CurriculumValidationError) as exc:
        print(exc)
        return 1

    print(
        "课程校验通过: "
        f"{len(catalog.roadmap.stages)} stages, "
        f"{len(catalog.roadmap.nodes)} roadmap nodes, "
        f"{len(catalog.pilot.nodes)} pilot nodes, "
        f"{len(catalog.assessment_set.assessments)} assessments"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
