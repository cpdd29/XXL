from __future__ import annotations

from typing import Any


RELEASE_CHANNEL_LABELS = {
    "stable": "正式",
    "canary": "灰度",
    "beta": "测试",
    "alpha": "内测",
    "deprecated": "弃用",
}

AUDIT_ACTION_LABELS = {
    "external_agent_registry.registered": "外接智能体已注册",
    "external_agent_registry.deleted": "外接智能体已移除",
    "external_skill_registry.registered": "外接 Skill 已注册",
    "external.agent.failure_reported": "外接智能体故障已上报",
    "external.skill.failure_reported": "外接 Skill 故障已上报",
    "external.agent.recovered": "外接智能体已恢复",
    "external.skill.recovered": "外接 Skill 已恢复",
    "external.agent.version_promoted": "外接智能体默认版本已切换",
    "external.skill.version_promoted": "外接 Skill 默认版本已切换",
    "external.agent.fallback_updated": "外接智能体回退版本已更新",
    "external.skill.fallback_updated": "外接 Skill 回退版本已更新",
    "external.agent.rollout_policy_updated": "外接智能体灰度策略已更新",
    "external.skill.rollout_policy_updated": "外接 Skill 灰度策略已更新",
    "external.agent.rollback_policy_updated": "外接智能体回滚策略已更新",
    "external.skill.rollback_policy_updated": "外接 Skill 回滚策略已更新",
    "external.agent.deprecation_updated": "外接智能体弃用状态已更新",
    "external.skill.deprecation_updated": "外接 Skill 弃用状态已更新",
    "agent.created": "智能体已创建",
    "agent.external.created": "外接智能体接入已创建",
    "agent.brain_skill.created": "内置 Skill 已创建",
    "agent.brain_skill.scope_updated": "内置 Skill 作用域已更新",
    "agent.brain_skill.deleted": "内置 Skill 已删除",
    "agent.deleted": "智能体已删除",
    "agent.enabled.updated": "智能体启用状态已更新",
    "agent.config.updated": "智能体配置已更新",
    "agent.reloaded": "智能体已重载",
    "approval.created": "审批单已创建",
    "approval.approved": "审批单已通过",
    "approval.rejected": "审批单已驳回",
    "approval.cancelled": "审批单已取消",
    "approval.executed": "审批单已执行",
    "tool_sources.scanned": "能力源已扫描",
    "tool_sources.skill_registered": "Skill 接入已登记",
    "tool_sources.mcp_registered": "MCP 接入已登记",
    "tool_sources.skill_updated": "Skill 接入已更新",
    "tool_sources.mcp_updated": "MCP 接入已更新",
    "tool_sources.tool_deleted": "能力接入项已删除",
    "executor.runtime.install_missing": "本地执行环境补装已触发",
    "executor.created": "执行器已创建",
    "executor.updated": "执行器已更新",
    "executor.deleted": "执行器已删除",
    "executor.validated": "执行器接入已校验",
    "executor.health_checked": "执行器健康检查已完成",
    "knowledge.vault.created": "知识仓已创建",
    "knowledge.vault.updated": "知识仓已更新",
    "knowledge.vault.deleted": "知识仓已删除",
    "knowledge.vault.imported": "知识仓内容已导入",
    "knowledge.vault.folder.created": "知识目录已创建",
    "knowledge.vault.entry.renamed": "知识条目已重命名",
    "knowledge.vault.entry.deleted": "知识条目已删除",
    "knowledge.vault.sync.completed": "知识仓同步已完成",
    "knowledge.vault.sync.failed": "知识仓同步失败",
    "settings.general.updated": "平台通用设置已更新",
    "settings.security_policy.update": "安全监听配置更新已发起",
    "settings.security_policy.updated": "安全监听配置已更新",
    "settings.agent_api.updated": "模型接入配置已更新",
    "settings.channel_integrations.updated": "渠道接入配置已更新",
    "security.penalty.manual.create": "安全处罚已创建",
    "security.penalty.release": "安全处罚已解除",
    "scheduler.dispatch_job.deleted": "调度遗留任务已清理",
    "scheduler.dispatch_claim.reclaimed": "调度分发租约已回收",
    "scheduler.run_claim.reclaimed": "运行租约已回收",
    "scheduler.workflow_execution_job.deleted": "工作流执行遗留任务已清理",
    "scheduler.workflow_execution_claim.reclaimed": "工作流执行租约已回收",
    "scheduler.workflow_execution_job.repaired": "工作流执行任务已修复",
    "scheduler.agent_execution_job.deleted": "智能体执行遗留任务已清理",
    "scheduler.agent_execution_claim.reclaimed": "智能体执行租约已回收",
    "scheduler.agent_execution_job.repaired": "智能体执行任务已修复",
    "event.replayed": "事件已重放",
    "workflow.manual_handoff": "任务已手动转交",
    "continue_active_task": "继续跟进当前任务",
    "clarify_request": "进入澄清流程",
    "handoff_to_execution": "已转入执行流程",
}

MODULE_LABELS = {
    "external_agent_registry.": "外接智能体治理",
    "external_skill_registry.": "外接 Skill 治理",
    "external.agent.": "外接智能体治理",
    "external.skill.": "外接 Skill 治理",
    "agent.": "智能体管理",
    "approval.": "审批中心",
    "tool_sources.": "能力接入",
    "executor.": "执行器管理",
    "knowledge.": "知识库管理",
    "settings.": "平台设置",
    "security.": "安全治理",
    "scheduler.": "调度自愈",
    "event.": "事件治理",
    "workflow.": "任务调度",
}

RESOURCE_LABELS = {
    "external_agent_registry": "外接智能体注册表",
    "external_skill_registry": "外接 Skill 注册表",
    "settings.security_policy": "安全监听配置",
    "settings.agent_api": "模型接入配置",
    "settings.channel_integrations": "渠道接入配置",
    "executor.runtime": "执行器运行环境",
    "security_rule": "安全规则",
    "security_penalty": "安全处罚",
    "security_incident_review": "安全事件复核",
    "认证系统": "认证系统",
}

RESOURCE_PREFIX_LABELS = (
    ("approval:", "审批单"),
    ("external.agent.", "外接智能体"),
    ("external.skill.", "外接 Skill"),
    ("agent.", "智能体"),
    ("brain_skill.", "内置 Skill"),
    ("executor.", "执行器"),
    ("knowledge.vault.", "知识仓"),
    ("tool_source.", "能力源"),
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _contains_cjk(value: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in value)


def _metadata(log: dict[str, Any]) -> dict[str, Any]:
    metadata = log.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _release_channel_label(value: Any) -> str | None:
    normalized = _text(value).lower()
    if not normalized:
        return None
    return RELEASE_CHANNEL_LABELS.get(normalized, normalized)


def _resource_label(raw_resource: str) -> str:
    if not raw_resource:
        return "系统资源"
    if raw_resource in RESOURCE_LABELS:
        return RESOURCE_LABELS[raw_resource]
    for prefix, label in RESOURCE_PREFIX_LABELS:
        if raw_resource.startswith(prefix):
            suffix = raw_resource[len(prefix) :].strip()
            return f"{label} · {suffix}" if suffix else label
    if _contains_cjk(raw_resource):
        return raw_resource
    if "." in raw_resource:
        return raw_resource.replace(".", " / ")
    return raw_resource


def _module_label(raw_action: str, raw_resource: str) -> str | None:
    for prefix, label in MODULE_LABELS.items():
        if raw_action.startswith(prefix):
            return label
    if raw_resource.startswith("approval:"):
        return "审批中心"
    if raw_resource.startswith("knowledge.vault."):
        return "知识库管理"
    if raw_resource.startswith("executor."):
        return "执行器管理"
    if raw_resource.startswith("agent."):
        return "智能体管理"
    return None


def _action_label(raw_action: str, raw_resource: str) -> str:
    if raw_action in AUDIT_ACTION_LABELS:
        return AUDIT_ACTION_LABELS[raw_action]
    if raw_resource == "security_rule" and raw_action in {"created", "updated", "rollback"}:
        return {
            "created": "安全规则已创建",
            "updated": "安全规则已更新",
            "rollback": "安全规则已回滚",
        }[raw_action]
    if _contains_cjk(raw_action):
        return raw_action
    if raw_action:
        return raw_action.replace("_", " ").replace(".", " / ")
    return "系统事件"


def _looks_like_machine_details(details: str) -> bool:
    if not details:
        return False
    if details.count("=") >= 2:
        return True
    if ";" in details and "=" in details:
        return True
    return False


def _registry_summary(log: dict[str, Any], *, capability_label: str, action_text: str) -> str:
    metadata = _metadata(log)
    entity_id = (
        _text(metadata.get("agent_id"))
        or _text(metadata.get("skill_id"))
        or _text(metadata.get("family"))
        or _text(metadata.get("agent_family"))
        or _text(metadata.get("skill_family"))
    )
    version = _text(metadata.get("version"))
    release_channel = _release_channel_label(metadata.get("release_channel"))
    compatibility = metadata.get("compatibility") if isinstance(metadata.get("compatibility"), list) else []
    compatibility_text = "、".join(_text(item) for item in compatibility if _text(item))
    summary = f"{capability_label} {entity_id or '未命名能力'} {action_text}"
    extras: list[str] = []
    if version:
        extras.append(f"版本 {version}")
    if release_channel:
        extras.append(f"发布通道 {release_channel}")
    if compatibility_text:
        extras.append(f"兼容 {compatibility_text}")
    if metadata.get("default_version") is True:
        extras.append("已设为默认版本")
    if metadata.get("deprecated") is True:
        extras.append("当前为弃用状态")
    if extras:
        summary = f"{summary}，" + "，".join(extras)
    return f"{summary}。"


def _operator_summary(log: dict[str, Any], *, action_label: str, resource_label: str) -> str:
    raw_action = _text(log.get("action"))
    details = _text(log.get("details"))
    metadata = _metadata(log)

    if raw_action == "external_agent_registry.registered":
        return _registry_summary(log, capability_label="外接智能体", action_text="已接入平台")
    if raw_action == "external_agent_registry.deleted":
        return _registry_summary(log, capability_label="外接智能体", action_text="已从平台移除")
    if raw_action == "external_skill_registry.registered":
        return _registry_summary(log, capability_label="外接 Skill", action_text="已接入平台")

    if details and not _looks_like_machine_details(details):
        return details

    if raw_action == "approval.created":
        return f"{resource_label} 已创建审批单，等待审核。"
    if raw_action == "approval.executed":
        return f"{resource_label} 已按审批结果执行。"

    if raw_action.startswith("external.agent.") or raw_action.startswith("external.skill."):
        subject = resource_label
        if details:
            return details.replace("Agent", "智能体").replace("Skill", "Skill")
        return f"{subject} 已完成“{action_label}”。"

    if raw_action == "settings.security_policy.update":
        return "安全监听配置变更已提交审批，待审核通过后生效。"

    if metadata:
        if raw_action == "executor.validated":
            message = _text(metadata.get("message"))
            if message:
                return f"{resource_label} 校验完成：{message}"

    if details:
        return details
    return f"{resource_label} 已发生“{action_label}”事件。"


def present_audit_log(log: dict[str, Any]) -> dict[str, Any]:
    raw_action = _text(log.get("action"))
    raw_resource = _text(log.get("resource"))
    action_label = _action_label(raw_action, raw_resource)
    resource_label = _resource_label(raw_resource)
    module_label = _module_label(raw_action, raw_resource)

    payload = dict(log)
    payload["action_label"] = action_label
    payload["resource_label"] = resource_label
    payload["module_label"] = module_label
    payload["operator_summary"] = _operator_summary(
        payload,
        action_label=action_label,
        resource_label=resource_label,
    )
    return payload


def present_audit_logs(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [present_audit_log(item) for item in items if isinstance(item, dict)]
