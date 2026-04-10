from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_check() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_list_tasks(auth_headers) -> None:
    response = client.get("/api/tasks", headers=auth_headers)
    body = response.json()

    assert response.status_code == 200
    assert body["total"] >= 1
    assert isinstance(body["items"], list)
