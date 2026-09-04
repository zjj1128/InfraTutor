from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.core.config import Settings
from backend.app.main import create_app


def _settings(tmp_path: Path, curriculum_copy: Path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'infratutor-test.db'}",
        curriculum_dir=curriculum_copy,
        cors_origins="http://localhost:5173",
    )


def test_health_check_and_sqlite_initialization(tmp_path: Path, curriculum_copy: Path) -> None:
    database_path = tmp_path / "infratutor-test.db"
    app = create_app(_settings(tmp_path, curriculum_copy))

    with TestClient(app) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "curriculum": "ready",
        "database": "ready",
    }
    assert database_path.exists()


def test_roadmap_endpoint_returns_nine_stages_and_pilot_nodes(
    tmp_path: Path, curriculum_copy: Path
) -> None:
    app = create_app(_settings(tmp_path, curriculum_copy))

    with TestClient(app) as client:
        response = client.get("/api/roadmap")

    assert response.status_code == 200
    payload = response.json()
    assert payload["stage_count"] == 9
    assert payload["pilot_node_count"] == 8
    assert payload["learner_state_available"] is True
    assert [stage["order"] for stage in payload["stages"]] == list(range(1, 10))

    stage_three = next(
        stage for stage in payload["stages"] if stage["id"] == "stage_3_ib_rdma_theory"
    )
    assert stage_three["availability"] == "in_progress"
    memory_registration = next(
        node for node in stage_three["nodes"] if node["id"] == "memory_registration"
    )
    assert memory_registration["availability"] == "available"
    assert memory_registration["learner_status"] == "locked"
    assert memory_registration["progress_status"] == "no_evidence"
    assert memory_registration["access_status"] == "locked"
    assert memory_registration["can_start_diagnostic_probe"] is True
    assert {item["id"] for item in memory_registration["missing_prerequisites"]} >= {
        "device_dma",
        "pinned_memory",
        "rdma_data_path",
    }
    assert {item["id"] for item in memory_registration["prerequisites"]} == {
        "pinned_memory",
        "hca_role",
        "rdma_data_path",
    }


def test_default_learner_and_reset_api_persist_across_restart(
    tmp_path: Path, curriculum_copy: Path
) -> None:
    settings = _settings(tmp_path, curriculum_copy)
    app = create_app(settings)

    with TestClient(app) as client:
        clean = client.get("/api/learner")
        assert clean.status_code == 200
        assert clean.json()["learner_id"] == "default_learner"
        assert len(clean.json()["node_states"]) == 121
        assert clean.json()["node_states"]["virtual_vs_physical_memory"]["status"] == "ready"
        assert (
            clean.json()["node_states"]["virtual_vs_physical_memory"]["progress_status"]
            == "no_evidence"
        )
        assert (
            clean.json()["node_states"]["virtual_vs_physical_memory"]["access_status"]
            == "available"
        )

        reset = client.post("/api/demo/reset", json={"seed": "golden_path"})
        assert reset.status_code == 200
        assert reset.json()["node_states"]["device_dma"]["status"] == "partial"
        assert reset.json()["node_states"]["memory_registration"]["status"] == "locked"
        assert reset.json()["node_states"]["memory_registration"]["progress_status"] == "learning"
        assert reset.json()["node_states"]["rdma_data_path"]["progress_status"] == "mastered"

    restarted_app = create_app(settings)
    with TestClient(restarted_app) as client:
        persisted = client.get("/api/learner").json()
        assert persisted["node_states"]["device_dma"]["mastery_score"] == 0.58
        assert persisted["node_states"]["device_dma"]["status"] == "partial"

        invalid = client.post("/api/demo/reset", json={"seed": "unknown"})
        assert invalid.status_code == 422

        clean_again = client.post("/api/demo/reset", json={"seed": "clean"}).json()
        assert clean_again["node_states"]["device_dma"]["status"] == "locked"
