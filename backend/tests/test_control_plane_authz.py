from fastapi import status
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketDenialResponse
from starlette.websockets import WebSocketDisconnect

from app.main import app


client = TestClient(app)


def test_protected_route_requires_bearer_token() -> None:
    response = client.get("/api/tasks", headers={"x-test-no-auth": "1"})

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json()["detail"] == "Missing bearer token"


def test_viewer_cannot_mutate_control_plane_resources(
    viewer_auth_headers: dict[str, str],
) -> None:
    response = client.post("/api/tasks/1/retry", headers=viewer_auth_headers)

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json()["detail"] == "Permission denied"


def test_public_message_ingest_route_remains_anonymous() -> None:
    response = client.post(
        "/api/messages/ingest",
        headers={"x-test-no-auth": "1"},
        json={
            "channel": "telegram",
            "platformUserId": "public-authz-user",
            "chatId": "public-authz-chat",
            "text": "please search the workflow security docs",
        },
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["ok"] is True


def test_protected_websocket_requires_bearer_token() -> None:
    try:
        with client.websocket_connect(
            "/api/workflows/workflow-1/realtime",
            headers={"x-test-no-auth": "1"},
        ):
            raise AssertionError("Expected websocket auth to fail")
    except WebSocketDenialResponse as exc:
        assert exc.status_code == status.HTTP_401_UNAUTHORIZED
        assert exc.text == '{"detail":"Missing bearer token"}'
    except WebSocketDisconnect as exc:
        assert exc.code == status.WS_1008_POLICY_VIOLATION
