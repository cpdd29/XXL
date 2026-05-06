from typing import Any, Literal

from pydantic import Field

from app.platform.contracts.api_model import APIModel


ExecutorDriverType = Literal["codex_cli", "claude_code_cli", "http_runner"]
LocalExecutorDriverType = Literal["codex_cli", "claude_code_cli"]
ExecutorRunMode = Literal["local", "remote"]
ExecutorWorkspacePolicy = Literal["tenant_sandbox", "fixed_path"]
ExecutorShellPermission = Literal["read_only", "limited_exec", "full_exec"]
ExecutorApprovalPolicy = Literal["auto", "confirm_on_risk", "always_confirm"]
ExecutorStatus = Literal["unknown", "online", "offline", "degraded"]


class Executor(APIModel):
    id: str
    name: str
    description: str = ""
    driver_type: ExecutorDriverType = "codex_cli"
    run_mode: ExecutorRunMode = "local"
    entry: str = ""
    health_path: str = ""
    workspace_policy: ExecutorWorkspacePolicy = "tenant_sandbox"
    shell_permission: ExecutorShellPermission = "limited_exec"
    approval_policy: ExecutorApprovalPolicy = "confirm_on_risk"
    blocked_commands: list[str] = Field(default_factory=list)
    timeout_seconds: int = 120
    enabled: bool = True
    status: ExecutorStatus = "unknown"
    last_validated_at: str | None = None
    last_health_at: str | None = None
    last_error: str | None = None
    validation_message: str | None = None
    version_info: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExecutorCreateRequest(APIModel):
    id: str | None = None
    name: str
    description: str = ""
    driver_type: ExecutorDriverType = "codex_cli"
    run_mode: ExecutorRunMode = "local"
    entry: str = ""
    health_path: str = ""
    workspace_policy: ExecutorWorkspacePolicy = "tenant_sandbox"
    shell_permission: ExecutorShellPermission = "limited_exec"
    approval_policy: ExecutorApprovalPolicy = "confirm_on_risk"
    blocked_commands: list[str] = Field(default_factory=list)
    timeout_seconds: int = 120
    enabled: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExecutorUpdateRequest(APIModel):
    name: str | None = None
    description: str | None = None
    driver_type: ExecutorDriverType | None = None
    run_mode: ExecutorRunMode | None = None
    entry: str | None = None
    health_path: str | None = None
    workspace_policy: ExecutorWorkspacePolicy | None = None
    shell_permission: ExecutorShellPermission | None = None
    approval_policy: ExecutorApprovalPolicy | None = None
    blocked_commands: list[str] | None = None
    timeout_seconds: int | None = None
    enabled: bool | None = None
    metadata: dict[str, Any] | None = None


class ExecutorListResponse(APIModel):
    items: list[Executor]
    total: int
    updated_at: str = ""


class ExecutorActionResponse(APIModel):
    ok: bool
    message: str
    executor: Executor


class ExecutorDeleteResponse(APIModel):
    ok: bool
    message: str
    executor_id: str


class ExecutorCheckResponse(APIModel):
    ok: bool
    message: str
    executor: Executor
    details: dict[str, Any] = Field(default_factory=dict)


class ExecutorRuntimeLocalDriver(APIModel):
    driver_type: LocalExecutorDriverType
    command: str
    installed: bool
    resolved_path: str | None = None
    version_info: str | None = None


class ExecutorRuntimeCapabilitiesResponse(APIModel):
    local_drivers: list[ExecutorRuntimeLocalDriver] = Field(default_factory=list)
    available_local_driver_types: list[LocalExecutorDriverType] = Field(default_factory=list)
    missing_local_driver_types: list[LocalExecutorDriverType] = Field(default_factory=list)
    remote_driver_types: list[Literal["http_runner"]] = Field(default_factory=lambda: ["http_runner"])
    detected_at: str


class ExecutorRuntimeInstallRequest(APIModel):
    targets: list[LocalExecutorDriverType] = Field(default_factory=list)


class ExecutorRuntimeInstallResult(APIModel):
    driver_type: LocalExecutorDriverType
    command: str
    package_name: str
    attempted: bool
    installed: bool
    resolved_path: str | None = None
    version_info: str | None = None
    message: str


class ExecutorRuntimeInstallResponse(APIModel):
    ok: bool
    message: str
    results: list[ExecutorRuntimeInstallResult] = Field(default_factory=list)
    capabilities: ExecutorRuntimeCapabilitiesResponse
