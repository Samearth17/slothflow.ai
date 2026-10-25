import os
import tempfile
from pathlib import Path

# Isolate SQLite state before importing the application.
tmp = tempfile.TemporaryDirectory()
os.environ["SLOTHFLOW_DB"] = str(Path(tmp.name) / "test.db")

from fastapi.testclient import TestClient
from app import app, init_db

client = TestClient(app)


def setup_function():
    init_db()
    with client as c:
        pass


def test_health_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_plan_works_without_ollama(monkeypatch):
    import app as app_module
    monkeypatch.setattr(app_module, "ollama_plan", lambda text: None)
    response = client.post("/api/plan", json={"text": "Finish report by tomorrow. Prepare for interview."})
    assert response.status_code == 200
    data = response.json()
    assert len(data["tasks"]) >= 2
    assert data["engine"] == "local-rules"


def test_create_update_and_delete_task():
    response = client.post("/api/tasks", json={"title": "Write tests", "priority": "high", "estimate_minutes": 25})
    assert response.status_code == 200
    task = response.json()
    assert task["title"] == "Write tests"
    task_id = task["id"]

    updated = client.patch(f"/api/tasks/{task_id}", json={"status": "done"})
    assert updated.status_code == 200
    assert updated.json()["status"] == "done"

    deleted = client.delete(f"/api/tasks/{task_id}")
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True


def test_blank_task_rejected():
    response = client.post("/api/tasks", json={"title": "   "})
    assert response.status_code == 422


def test_daily_reset_counts_open_tasks():
    client.post("/api/tasks", json={"title": "Open task", "estimate_minutes": 15})
    client.post("/api/tasks", json={"title": "Finished task", "estimate_minutes": 25})
    tasks = client.get("/api/tasks").json()
    second = next(t for t in tasks if t["title"] == "Finished task")
    client.patch(f"/api/tasks/{second['id']}", json={"status": "done"})
    reset = client.get("/api/reset")
    assert reset.status_code == 200
    assert reset.json()["open_count"] >= 1
    assert any(t["title"] == "Open task" for t in reset.json()["tasks"])
