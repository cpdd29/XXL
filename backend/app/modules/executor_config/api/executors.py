from typing import Any

from fastapi import APIRouter, Depends

from app.modules.executor_config.schemas.executors import (
    Executor,
    ExecutorActionResponse,
    ExecutorCheckResponse,
    ExecutorCreateRequest,
    ExecutorDeleteResponse,
    ExecutorListResponse,
    ExecutorRuntimeCapabilitiesResponse,
    ExecutorRuntimeInstallRequest,
    ExecutorRuntimeInstallResponse,
    ExecutorUpdateRequest,
)
from app.modules.executor_config.service.executor_service import (
    create_executor,
    delete_executor,
    get_executor_runtime_capabilities,
    get_executor,
    health_check_executor,
    install_missing_local_drivers,
    list_executors,
    update_executor,
    validate_executor,
)
from app.platform.audit.control_plane_audit_service import append_control_plane_audit_log
from app.platform.auth.authz import require_authenticated_user, require_permission


router = APIRouter(dependencies=[Depends(require_authenticated_user)])


def _operator_identity(current_user: dict[str, Any]) -> str:
    return (
        str(current_user.get("email") or "").strip()
        or str(current_user.get("id") or "").strip()
        or "system"
    )


@router.get(
    "",
    response_model=ExecutorListResponse,
    dependencies=[Depends(require_permission("settings:read"))],
)
def list_executors_route() -> ExecutorListResponse:
    return ExecutorListResponse(**list_executors())


@router.get(
    "/runtime/capabilities",
    response_model=ExecutorRuntimeCapabilitiesResponse,
    dependencies=[Depends(require_permission("settings:read"))],
)
def get_runtime_capabilities_v2_route() -> ExecutorRuntimeCapabilitiesResponse:
    return ExecutorRuntimeCapabilitiesResponse(**get_executor_runtime_capabilities())


@router.get(
    "/runtime-capabilities",
    response_model=ExecutorRuntimeCapabilitiesResponse,
    dependencies=[Depends(require_permission("settings:read"))],
)
def get_runtime_capabilities_route() -> ExecutorRuntimeCapabilitiesResponse:
    return ExecutorRuntimeCapabilitiesResponse(**get_executor_runtime_capabilities())


@router.post(
    "/runtime/install-missing",
    response_model=ExecutorRuntimeInstallResponse,
    dependencies=[Depends(require_permission("settings:write"))],
)
def install_runtime_missing_route(
    payload: ExecutorRuntimeInstallRequest,
    current_user: dict[str, Any] = Depends(require_authenticated_user),
) -> ExecutorRuntimeInstallResponse:
    response = ExecutorRuntimeInstallResponse(
        **install_missing_local_drivers(payload.model_dump(exclude_none=True))
    )
    append_control_plane_audit_log(
        action="executor.runtime.install_missing",
        user=_operator_identity(current_user),
        resource="executor.runtime",
        details=response.message,
        metadata={"results": [item.model_dump() for item in response.results]},
    )
    return response


@router.get(
    "/{executor_id}",
    response_model=Executor,
    dependencies=[Depends(require_permission("settings:read"))],
)
def get_executor_route(executor_id: str) -> Executor:
    return Executor(**get_executor(executor_id))


@router.post(
    "",
    response_model=ExecutorActionResponse,
    dependencies=[Depends(require_permission("settings:write"))],
)
def create_executor_route(
    payload: ExecutorCreateRequest,
    current_user: dict[str, Any] = Depends(require_authenticated_user),
) -> ExecutorActionResponse:
    response = ExecutorActionResponse(**create_executor(payload.model_dump(exclude_none=True)))
    append_control_plane_audit_log(
        action="executor.created",
        user=_operator_identity(current_user),
        resource=f"executor.{response.executor.id}",
        details=f"新增执行器 {response.executor.name}",
    )
    return response


@router.put(
    "/{executor_id}",
    response_model=ExecutorActionResponse,
    dependencies=[Depends(require_permission("settings:write"))],
)
def update_executor_route(
    executor_id: str,
    payload: ExecutorUpdateRequest,
    current_user: dict[str, Any] = Depends(require_authenticated_user),
) -> ExecutorActionResponse:
    response = ExecutorActionResponse(
        **update_executor(executor_id, payload.model_dump(exclude_none=True))
    )
    append_control_plane_audit_log(
        action="executor.updated",
        user=_operator_identity(current_user),
        resource=f"executor.{executor_id}",
        details=f"更新执行器 {response.executor.name}",
    )
    return response


@router.delete(
    "/{executor_id}",
    response_model=ExecutorDeleteResponse,
    dependencies=[Depends(require_permission("settings:write"))],
)
def delete_executor_route(
    executor_id: str,
    current_user: dict[str, Any] = Depends(require_authenticated_user),
) -> ExecutorDeleteResponse:
    response = ExecutorDeleteResponse(**delete_executor(executor_id))
    append_control_plane_audit_log(
        action="executor.deleted",
        user=_operator_identity(current_user),
        resource=f"executor.{executor_id}",
        details=f"删除执行器 {executor_id}",
    )
    return response


@router.post(
    "/{executor_id}/validate",
    response_model=ExecutorCheckResponse,
    dependencies=[Depends(require_permission("settings:write"))],
)
def validate_executor_route(
    executor_id: str,
    current_user: dict[str, Any] = Depends(require_authenticated_user),
) -> ExecutorCheckResponse:
    response = ExecutorCheckResponse(**validate_executor(executor_id))
    append_control_plane_audit_log(
        action="executor.validated",
        user=_operator_identity(current_user),
        resource=f"executor.{executor_id}",
        details=f"校验执行器 {executor_id}: {response.message}",
        metadata=response.details,
    )
    return response


@router.post(
    "/{executor_id}/health-check",
    response_model=ExecutorCheckResponse,
    dependencies=[Depends(require_permission("settings:write"))],
)
def health_check_executor_route(
    executor_id: str,
    current_user: dict[str, Any] = Depends(require_authenticated_user),
) -> ExecutorCheckResponse:
    response = ExecutorCheckResponse(**health_check_executor(executor_id))
    append_control_plane_audit_log(
        action="executor.health_checked",
        user=_operator_identity(current_user),
        resource=f"executor.{executor_id}",
        details=f"执行器健康检查 {executor_id}: {response.message}",
        metadata=response.details,
    )
    return response
