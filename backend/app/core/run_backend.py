import uvicorn

from backend.app.core.config import Settings


def main() -> int:
    settings = Settings()
    uvicorn.run(
        "backend.app.main:app",
        host=settings.backend_host,
        port=settings.backend_port,
        reload=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
