from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, event, inspect, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.db.base import Base


def create_database_engine(database_url: str) -> Engine:
    if database_url.startswith("sqlite:///") and not database_url.endswith(":memory:"):
        database_path = Path(database_url.removeprefix("sqlite:///"))
        database_path.parent.mkdir(parents=True, exist_ok=True)

    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    engine_options: dict[str, Any] = {"connect_args": connect_args}
    if database_url in {"sqlite://", "sqlite:///:memory:"}:
        engine_options["poolclass"] = StaticPool

    engine = create_engine(database_url, **engine_options)
    if database_url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _enable_sqlite_foreign_keys(dbapi_connection: Any, _: Any) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def initialize_database(engine: Engine) -> None:
    # Import every model before create_all so standalone scripts and tests get
    # the same metadata registration as the FastAPI application.
    from backend.app.learner import models as learner_models  # noqa: F401
    from backend.app.llm import models as llm_models  # noqa: F401
    from backend.app.sessions import models as session_models  # noqa: F401
    from backend.app.tutor import models as tutor_models  # noqa: F401

    Base.metadata.create_all(engine)
    if (
        engine.dialect.name != "sqlite"
        or "learning_sessions" not in inspect(engine).get_table_names()
    ):
        return

    columns = {item["name"] for item in inspect(engine).get_columns("learning_sessions")}
    additions = {
        "entry_mode": "VARCHAR(24) NOT NULL DEFAULT 'normal'",
        "version": "INTEGER NOT NULL DEFAULT 1",
        "recoverable_error_json": "JSON",
    }
    with engine.begin() as connection:
        for name, definition in additions.items():
            if name not in columns:
                connection.execute(
                    text(f"ALTER TABLE learning_sessions ADD COLUMN {name} {definition}")
                )
