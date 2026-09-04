from __future__ import annotations

import errno
import socket
import sqlite3
import sys
from pathlib import Path

from backend.app.core.config import PROJECT_ROOT, Settings


def _check_port(label: str, host: str, port: int) -> None:
    bind_host = "0.0.0.0" if host in {"0.0.0.0", "localhost"} else host
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind((bind_host, port))
    except OSError as exc:
        if exc.errno == errno.EADDRINUSE:
            print(
                f"{label} 端口 {host}:{port} 已被占用；请释放端口或显式修改配置。",
                file=sys.stderr,
            )
        else:
            print(
                f"无法检查 {label} 端口 {host}:{port}: {exc.strerror}",
                file=sys.stderr,
            )
        raise SystemExit(2) from exc


def _current_seed(database_url: str) -> str:
    prefix = "sqlite:///"
    if not database_url.startswith(prefix) or database_url.endswith(":memory:"):
        return "unknown"
    raw_path = database_url.removeprefix(prefix)
    path = Path(raw_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    if not path.exists():
        return "clean (首次启动)"
    try:
        with sqlite3.connect(path) as connection:
            row = connection.execute(
                "SELECT active_seed FROM learners WHERE id = ?", ("default_learner",)
            ).fetchone()
    except sqlite3.Error:
        return "clean (待初始化)"
    return str(row[0]) if row else "clean (待初始化)"


def main() -> int:
    settings = Settings()
    _check_port("Backend", settings.backend_host, settings.backend_port)
    _check_port("Frontend", settings.frontend_host, settings.frontend_port)
    print(settings.backend_host)
    print(settings.backend_port)
    print(settings.frontend_host)
    print(settings.frontend_port)
    print(settings.llm_mode)
    print(_current_seed(settings.database_url))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
