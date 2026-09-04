from __future__ import annotations

import json
from pathlib import Path

from backend.app.core.config import PROJECT_ROOT
from backend.app.llm.contracts import AssessmentResult, TutorMessageResult

SCHEMAS = {
    "assessment_output.schema.json": AssessmentResult,
    "tutor_message_output.schema.json": TutorMessageResult,
}


def schema_documents() -> dict[str, dict[str, object]]:
    return {filename: model.model_json_schema() for filename, model in SCHEMAS.items()}


def write_schemas(schema_dir: Path = PROJECT_ROOT / "schemas") -> None:
    for filename, document in schema_documents().items():
        path = schema_dir / filename
        path.write_text(
            json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def main() -> int:
    write_schemas()
    print("Generated LLM schemas from Pydantic contracts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
