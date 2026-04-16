from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_operator_can_create_and_process_approval(auth_headers_factory) -> None:
    headers = auth_headers_factory(role="operator", email="ops@example.test")

    create_response = client.post(
        "/api/approvals",
        json={
            "requestType": "settings_change",
            "title": "更新主脑通用配置",
            "resource": "settings.general",
            "reason": "需要提高刷新频率",
            "payload": {"dashboardAutoRefresh": False},
        },
        headers=headers,
    )

    assert create_response.status_code == 200
    approval = create_response.json()["approval"]
    assert approval["status"] == "pending"

    list_response = client.get("/api/approvals?status=pending", headers=headers)
    assert list_response.status_code == 200
    assert list_response.json()["total"] >= 1

    approve_response = client.post(
        f"/api/approvals/{approval['id']}/approve",
        json={"note": "允许执行"},
        headers=headers,
    )
    assert approve_response.status_code == 200
    assert approve_response.json()["approval"]["status"] == "approved"


def test_viewer_can_read_but_cannot_write_approvals(auth_headers_factory) -> None:
    viewer_headers = auth_headers_factory(role="viewer", email="viewer@example.test")

    read_response = client.get("/api/approvals", headers=viewer_headers)
    assert read_response.status_code == 200

    write_response = client.post(
        "/api/approvals",
        json={
            "requestType": "manual_handoff",
            "title": "人工接管工作流",
            "resource": "workflow.run",
        },
        headers=viewer_headers,
    )
    assert write_response.status_code == 403
