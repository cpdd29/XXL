from __future__ import annotations

from app.services.free_workflow_service import FreeWorkflowService
from app.services.skill_registry_service import SkillRegistryService
from app.services.skill_runtime_service import SkillRuntimeService


def _build_service() -> FreeWorkflowService:
    registry = SkillRegistryService()
    runtime = SkillRuntimeService(registry=registry)
    return FreeWorkflowService(registry=registry, runtime=runtime)


class _MCPRuntimeStub:
    def __init__(self, *, fail_primary: bool = False) -> None:
        self.fail_primary = fail_primary
        self.shadow_invocations: list[dict] = []

    def build_tool_mapping(self, *, refresh: bool = False) -> dict[str, dict]:
        _ = refresh
        return {
            "agent-reach-external:web_search": {
                "id": "agent-reach-external:web_search",
                "name": "web_search",
                "source": "agent-reach-external",
            },
            "agent-reach-external:pdf_read": {
                "id": "agent-reach-external:pdf_read",
                "name": "pdf_read",
                "source": "agent-reach-external",
            },
            "agent-reach-external:pdf_summary": {
                "id": "agent-reach-external:pdf_summary",
                "name": "pdf_summary",
                "source": "agent-reach-external",
            },
            "agent-reach-external:weather": {
                "id": "agent-reach-external:weather",
                "name": "weather_lookup",
                "source": "agent-reach-external",
            },
            "agent-reach-external:writer_speech": {
                "id": "agent-reach-external:writer_speech",
                "name": "speech_writer",
                "source": "agent-reach-external",
            },
            "agent-reach-external:writer_general": {
                "id": "agent-reach-external:writer_general",
                "name": "general_writer",
                "source": "agent-reach-external",
            },
        }

    def invoke_tool(self, *, tool_id: str, payload: dict | None = None, trace_context: dict | None = None, **kwargs):  # noqa: ANN001
        _ = kwargs
        if self.fail_primary:
            return {
                "ok": False,
                "trace_id": "trace-runtime-failed",
                "duration_ms": 1.2,
                "error": {"type": "RuntimeError", "message": "runtime unavailable"},
            }
        return {
            "ok": True,
            "trace_id": "trace-runtime-ok",
            "duration_ms": 1.1,
            "result": {"tool": tool_id, "payload": payload or {}, "trace_context": trace_context or {}},
        }

    def invoke_shadow_tool(self, *, tool_id: str, payload: dict | None = None, trace_context: dict | None = None, **kwargs):  # noqa: ANN001
        _ = kwargs
        self.shadow_invocations.append(
            {"tool_id": tool_id, "payload": payload or {}, "trace_context": trace_context or {}}
        )
        return {
            "ok": True,
            "trace_id": "trace-runtime-shadow",
            "duration_ms": 1.0,
            "result": {"tool": tool_id},
        }


class _MCPRuntimeNoMappingStub(_MCPRuntimeStub):
    def build_tool_mapping(self, *, refresh: bool = False) -> dict[str, dict]:
        _ = refresh
        return {}


class _MCPRuntimeMixedMappingStub(_MCPRuntimeStub):
    def build_tool_mapping(self, *, refresh: bool = False) -> dict[str, dict]:
        mapping = super().build_tool_mapping(refresh=refresh)
        mapping["clawempire-skill-pack-web-research-report"] = {
            "id": "clawempire-skill-pack-web-research-report",
            "name": "web_research_report_skill_pack",
            "type": "skill",
            "source": "clawempire-skill-library",
        }
        return mapping


class _MCPLegacyOnlyMappingStub(_MCPRuntimeStub):
    def build_tool_mapping(self, *, refresh: bool = False) -> dict[str, dict]:
        _ = refresh
        return {
            "local-mcp-services:web_search": {
                "id": "local-mcp-services:web_search",
                "name": "web_search",
                "source": "local-mcp-services",
            }
        }


def test_free_workflow_registers_builtin_skills() -> None:
    service = _build_service()
    names = {item["name"] for item in service.list_skills()}
    assert names == {
        "task_status_skill",
        "task_list_skill",
    }


def test_free_workflow_external_only_registers_only_readonly_builtin_skills(monkeypatch) -> None:
    monkeypatch.setenv("WORKBOT_TOOL_SOURCES_MODE", "external_only")
    service = _build_service()
    names = {item["name"] for item in service.list_skills()}
    assert names == {
        "task_status_skill",
        "task_list_skill",
    }


def test_task_status_and_task_list_skills() -> None:
    service = _build_service()

    status_result = service.execute_skill("task_status_skill")
    assert status_result["ok"] is True
    assert status_result["result"]["in_progress_count"] >= 1
    assert isinstance(status_result["result"]["items"], list)

    list_result = service.execute_skill("task_list_skill", payload={"limit": 3})
    assert list_result["ok"] is True
    assert len(list_result["result"]["items"]) == 3
    assert list_result["result"]["total"] >= 3


def test_weather_and_web_search_route_through_runtime_when_runtime_is_available() -> None:
    registry = SkillRegistryService()
    runtime = SkillRuntimeService(registry=registry)
    service = FreeWorkflowService(registry=registry, runtime=runtime, mcp_runtime=_MCPRuntimeStub())

    weather = service.run(text="今天广州天气怎么样？")
    assert weather["ok"] is True
    assert weather["selected_skill"] == "weather_skill"
    assert weather["migration_runtime"]["selected_path"] == "runtime"
    assert weather["result"]["source"] == "mcp_runtime"

    search = service.run(text="帮我搜索 AI agent 最佳实践")
    assert search["ok"] is True
    assert search["selected_skill"] == "web_search_skill"
    assert search["migration_runtime"]["selected_path"] == "runtime"
    assert search["result"]["source"] == "mcp_runtime"


def test_pdf_read_and_pdf_summary_route_through_runtime_when_runtime_is_available() -> None:
    registry = SkillRegistryService()
    runtime = SkillRuntimeService(registry=registry)
    service = FreeWorkflowService(registry=registry, runtime=runtime, mcp_runtime=_MCPRuntimeStub())
    fake_pdf = (
        b"%PDF-1.4\n"
        b"1 0 obj << /Type /Page >> endobj\n"
        b"BT /F1 12 Tf (Hello PDF world. This is a workflow summary example.) Tj ET\n"
    )

    read_result = service.execute_skill("pdf_read_skill", payload={"bytes": fake_pdf})
    assert read_result["ok"] is True
    assert read_result["migration_runtime"]["selected_path"] == "runtime"
    assert read_result["result"]["source"] == "mcp_runtime"

    summary_result = service.execute_skill("pdf_summary_skill", payload={"bytes": fake_pdf})
    assert summary_result["ok"] is True
    assert summary_result["migration_runtime"]["selected_path"] == "runtime"
    assert summary_result["result"]["source"] == "mcp_runtime"


def test_speech_and_general_writer_route_through_runtime_when_runtime_is_available() -> None:
    registry = SkillRegistryService()
    runtime = SkillRuntimeService(registry=registry)
    service = FreeWorkflowService(registry=registry, runtime=runtime, mcp_runtime=_MCPRuntimeStub())

    speech = service.run(text="帮我写一段关于团队协作的演讲稿")
    assert speech["ok"] is True
    assert speech["selected_skill"] == "speech_writer_skill"
    assert speech["migration_runtime"]["selected_path"] == "runtime"
    assert speech["result"]["source"] == "mcp_runtime"

    writing = service.run(text="给我生成一段项目复盘文案")
    assert writing["ok"] is True
    assert writing["selected_skill"] == "general_writer_skill"
    assert writing["migration_runtime"]["selected_path"] == "runtime"
    assert writing["result"]["source"] == "mcp_runtime"


def test_free_workflow_prefers_required_capability_match() -> None:
    service = _build_service()

    result = service.run(
        text="",
        required_capabilities=["task_status"],
    )
    assert result["ok"] is True
    assert result["selected_skill"] == "task_status_skill"
    assert result["selection_reason"] == "required_capabilities_match"


def test_free_workflow_runtime_primary_fallbacks_to_builtin_when_runtime_fails(monkeypatch) -> None:
    registry = SkillRegistryService()
    runtime = SkillRuntimeService(registry=registry)
    service = FreeWorkflowService(registry=registry, runtime=runtime, mcp_runtime=_MCPRuntimeStub(fail_primary=True))

    result = service.run(
        text="给我生成一段项目复盘文案",
        payload={"runtime_policy": {"mode": "runtime_primary", "shadow_mode": True}},
    )

    assert result["ok"] is False
    assert result["selected_skill"] == "general_writer_skill"
    assert result["migration_runtime"]["mode"] == "runtime_primary"
    assert result["migration_runtime"]["selected_path"] == "builtin_fallback"
    assert result["migration_runtime"]["fallback_reason"]
    assert result["error"]["code"] == "ability_not_found"


def test_free_workflow_runtime_primary_prefers_external_for_weather_and_writer() -> None:
    registry = SkillRegistryService()
    runtime = SkillRuntimeService(registry=registry)
    service = FreeWorkflowService(registry=registry, runtime=runtime, mcp_runtime=_MCPRuntimeStub())

    weather = service.execute_skill(
        "weather_skill",
        payload={"location": "Guangzhou", "runtime_policy": {"mode": "runtime_primary"}},
    )
    assert weather["ok"] is True
    assert weather["migration_runtime"]["selected_path"] == "runtime"
    assert weather["result"]["source"] == "mcp_runtime"

    speech = service.execute_skill(
        "speech_writer_skill",
        payload={"topic": "团队协作", "runtime_policy": {"mode": "runtime_primary"}},
    )
    assert speech["ok"] is True
    assert speech["migration_runtime"]["selected_path"] == "runtime"
    assert speech["result"]["source"] == "mcp_runtime"
    assert speech["migration_runtime"]["runtime_tool_id"] == "agent-reach-external:writer_speech"

    writing = service.execute_skill(
        "general_writer_skill",
        payload={"prompt": "项目复盘", "runtime_policy": {"mode": "runtime_primary"}},
    )
    assert writing["ok"] is True
    assert writing["migration_runtime"]["selected_path"] == "runtime"
    assert writing["result"]["source"] == "mcp_runtime"
    assert writing["migration_runtime"]["runtime_tool_id"] == "agent-reach-external:writer_general"


def test_free_workflow_runtime_tool_resolution_ignores_skill_like_catalog_entries() -> None:
    registry = SkillRegistryService()
    runtime = SkillRuntimeService(registry=registry)
    service = FreeWorkflowService(registry=registry, runtime=runtime, mcp_runtime=_MCPRuntimeMixedMappingStub())

    result = service.run(
        text="帮我搜索 AI agent 最佳实践",
        payload={"runtime_policy": {"mode": "runtime_primary"}},
    )

    assert result["ok"] is True
    assert result["selected_skill"] == "web_search_skill"
    assert result["migration_runtime"]["selected_path"] == "runtime"
    assert result["migration_runtime"]["runtime_tool_id"] == "agent-reach-external:web_search"


def test_free_workflow_runtime_tool_resolution_skips_legacy_fallback_sources_by_default(monkeypatch) -> None:
    monkeypatch.setenv("WORKBOT_TOOL_SOURCES_MODE", "hybrid")
    registry = SkillRegistryService()
    runtime = SkillRuntimeService(registry=registry)
    service = FreeWorkflowService(registry=registry, runtime=runtime, mcp_runtime=_MCPLegacyOnlyMappingStub())

    result = service.run(
        text="帮我搜索 AI agent 最佳实践",
        payload={"runtime_policy": {"mode": "runtime_primary"}},
    )

    assert result["ok"] is False
    assert result["selected_skill"] == "web_search_skill"
    assert result["migration_runtime"]["selected_path"] == "builtin"
    assert result["migration_runtime"]["runtime_tool_id"] is None
    assert result["error"]["code"] == "ability_not_found"


def test_free_workflow_runtime_tool_resolution_allows_legacy_fallback_in_local_only(monkeypatch) -> None:
    monkeypatch.setenv("WORKBOT_TOOL_SOURCES_MODE", "local_only")
    registry = SkillRegistryService()
    runtime = SkillRuntimeService(registry=registry)
    service = FreeWorkflowService(registry=registry, runtime=runtime, mcp_runtime=_MCPLegacyOnlyMappingStub())

    result = service.run(
        text="帮我搜索 AI agent 最佳实践",
        payload={"runtime_policy": {"mode": "runtime_primary"}},
    )

    assert result["ok"] is True
    assert result["selected_skill"] == "web_search_skill"
    assert result["migration_runtime"]["selected_path"] == "runtime"
    assert result["migration_runtime"]["runtime_tool_id"] == "local-mcp-services:web_search"


def test_free_workflow_strict_external_requires_runtime_tool(monkeypatch) -> None:
    monkeypatch.setenv("WORKBOT_STRICT_EXTERNAL_SKILLS", "true")
    registry = SkillRegistryService()
    runtime = SkillRuntimeService(registry=registry)
    service = FreeWorkflowService(registry=registry, runtime=runtime, mcp_runtime=_MCPRuntimeNoMappingStub())

    result = service.run(text="帮我搜索 AI agent 最佳实践")

    assert result["ok"] is False
    assert result["selected_skill"] == "web_search_skill"
    assert result["migration_runtime"]["selected_path"] == "external_runtime_required"
    assert result["migration_runtime"]["strict_external_required"] is True
    assert result["error"]["code"] == "external_runtime_required"
    assert "runtime tool not found" in result["error"]["message"]


def test_free_workflow_external_only_requires_runtime_tool_without_extra_flag(monkeypatch) -> None:
    monkeypatch.setenv("WORKBOT_TOOL_SOURCES_MODE", "external_only")
    registry = SkillRegistryService()
    runtime = SkillRuntimeService(registry=registry)
    service = FreeWorkflowService(registry=registry, runtime=runtime, mcp_runtime=_MCPRuntimeNoMappingStub())

    result = service.run(text="帮我搜索 AI agent 最佳实践")

    assert result["ok"] is False
    assert result["selected_skill"] == "web_search_skill"
    assert result["migration_runtime"]["selected_path"] == "external_runtime_required"
    assert result["migration_runtime"]["strict_external_required"] is True
    assert result["error"]["code"] == "external_runtime_required"


def test_free_workflow_external_only_still_routes_weather_through_runtime_without_builtin_registration(monkeypatch) -> None:
    monkeypatch.setenv("WORKBOT_TOOL_SOURCES_MODE", "external_only")
    registry = SkillRegistryService()
    runtime = SkillRuntimeService(registry=registry)
    service = FreeWorkflowService(registry=registry, runtime=runtime, mcp_runtime=_MCPRuntimeStub())

    result = service.run(text="今天广州天气怎么样？")

    assert result["ok"] is True
    assert result["selected_skill"] == "weather_skill"
    assert result["migration_runtime"]["selected_path"] == "runtime"
    assert result["result"]["source"] == "mcp_runtime"


def test_free_workflow_strict_external_disables_builtin_fallback_on_runtime_failure(monkeypatch) -> None:
    monkeypatch.setenv("WORKBOT_STRICT_EXTERNAL_SKILLS", "true")
    import app.services.free_workflow_service as free_workflow_module

    monkeypatch.setattr(free_workflow_module, "_http_get_json", lambda url, *, timeout_seconds: None)
    registry = SkillRegistryService()
    runtime = SkillRuntimeService(registry=registry)
    service = FreeWorkflowService(registry=registry, runtime=runtime, mcp_runtime=_MCPRuntimeStub(fail_primary=True))

    result = service.run(text="帮我搜索 AI agent 最佳实践")

    assert result["ok"] is False
    assert result["selected_skill"] == "web_search_skill"
    assert result["migration_runtime"]["selected_path"] == "external_runtime_required"
    assert result["error"]["code"] == "external_runtime_required"
    assert result["result"]["source"] == "external_runtime_required"


def test_free_workflow_external_only_disables_builtin_fallback_on_runtime_failure(monkeypatch) -> None:
    monkeypatch.setenv("WORKBOT_TOOL_SOURCES_MODE", "external_only")
    import app.services.free_workflow_service as free_workflow_module

    monkeypatch.setattr(free_workflow_module, "_http_get_json", lambda url, *, timeout_seconds: None)
    registry = SkillRegistryService()
    runtime = SkillRuntimeService(registry=registry)
    service = FreeWorkflowService(registry=registry, runtime=runtime, mcp_runtime=_MCPRuntimeStub(fail_primary=True))

    result = service.run(text="帮我搜索 AI agent 最佳实践")

    assert result["ok"] is False
    assert result["selected_skill"] == "web_search_skill"
    assert result["migration_runtime"]["selected_path"] == "external_runtime_required"
    assert result["migration_runtime"]["strict_external_required"] is True
    assert result["error"]["code"] == "external_runtime_required"


def test_free_workflow_strict_external_keeps_non_runtime_eligible_skills(monkeypatch) -> None:
    monkeypatch.setenv("WORKBOT_STRICT_EXTERNAL_SKILLS", "true")
    service = _build_service()

    result = service.execute_skill("task_status_skill")

    assert result["ok"] is True
    assert result["selected_skill"] == "task_status_skill"
