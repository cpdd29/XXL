from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4


INTENT_SIGNAL_RULES: dict[str, tuple[tuple[str, int], ...]] = {
    "search": (
        ("search", 4),
        ("find", 4),
        ("lookup", 4),
        ("research", 4),
        ("查", 4),
        ("搜索", 4),
        ("检索", 4),
        ("文档", 2),
        ("资料", 2),
        ("规范", 2),
        ("知识库", 2),
    ),
    "write": (
        ("write", 4),
        ("draft", 4),
        ("reply", 4),
        ("email", 4),
        ("announcement", 4),
        ("写", 4),
        ("生成", 3),
        ("草稿", 3),
        ("回复", 3),
        ("邮件", 3),
        ("公告", 3),
        ("总结", 2),
    ),
    "help": (
        ("help", 3),
        ("how", 3),
        ("what", 2),
        ("why", 2),
        ("explain", 3),
        ("guide", 2),
        ("帮助", 3),
        ("如何", 3),
        ("怎么", 3),
        ("为什么", 2),
        ("说明", 2),
        ("解释", 2),
    ),
}
CHAT_GREETING_HINTS = {
    "hi",
    "hello",
    "hey",
    "你好",
    "您好",
    "嗨",
    "哈喽",
    "在吗",
}
CHAT_SMALL_TALK_HINTS = {
    "你是谁",
    "你是什么模型",
    "你用的什么模型",
    "你是哪个模型",
    "你是干嘛的",
    "你能做什么",
    "你可以做什么",
    "介绍一下你自己",
    "how are you",
    "what can you do",
    "who are you",
}
CHAT_CLARIFICATION_HINTS = {
    "什么意思",
    "啥意思",
    "再说一遍",
    "说清楚点",
    "解释一下",
    "详细一点",
    "具体一点",
    "why",
    "what do you mean",
    "clarify",
}
CHAT_FOLLOW_UP_HINTS = {
    "继续",
    "接着",
    "顺着这个",
    "补充一下",
    "follow up",
    "continue",
}
DIRECT_QUESTION_HINTS = {
    "怎么",
    "怎么样",
    "如何",
    "为啥",
    "为什么",
    "多少",
    "几号",
    "几点",
    "哪里",
    "哪儿",
    "有没有",
    "是否",
    "行不行",
    "可不可以",
    "吗",
    "呢",
    "what",
    "why",
    "how",
    "when",
    "where",
    "which",
    "is it",
    "can it",
}
RECEPTION_CLARIFY_HINTS = {
    "想聊",
    "想聊聊",
    "想请教",
    "想问问",
    "想咨询",
    "想了解",
    "想看看",
    "能不能",
    "可以吗",
    "方便吗",
    "帮我看看",
    "聊一下",
    "说一下",
    "talk",
    "chat",
    "can you",
    "could you",
}
WORKFLOW_OR_DIRECT_HINTS = {
    "工作流",
    "workflow",
    "agent",
    "执行",
    "调度",
    "路由",
    "dispatch",
}
PROJECT_DOMAIN_HINTS = {
    "workbot",
    "workflow",
    "agent",
    "钉钉",
    "dingtalk",
    "机器人",
    "接入",
    "配置",
    "日志",
    "文档",
    "资料",
    "知识库",
    "项目",
    "代码",
    "仓库",
    "接口",
    "api",
    "redis",
    "nats",
    "chroma",
    "webhook",
    "模板",
    "模版",
    "路由",
    "调度",
    "执行",
    "排查",
    "修复",
    "问题定位",
    "任务",
    "工作流",
}
LIVE_INFORMATION_HINTS = {
    "天气",
    "气温",
    "温度",
    "下雨",
    "预报",
    "台风",
    "新闻",
    "股价",
    "股票",
    "汇率",
    "路况",
    "航班",
    "hot search",
    "weather",
    "forecast",
    "temperature",
    "news",
    "stock",
    "exchange rate",
    "traffic",
    "flight",
}
HARD_TASK_REQUEST_HINTS = {
    "写一个",
    "写一段",
    "写一版",
    "写一封",
    "写一份",
    "写个",
    "生成",
    "整理",
    "总结",
    "翻译",
    "排查",
    "修复",
    "debug",
    "fix",
    "write",
    "draft",
    "generate",
    "summarize",
    "translate",
}
SEARCH_TASK_HINTS = {
    "search",
    "find",
    "lookup",
    "research",
    "查",
    "查一下",
    "查看",
    "搜",
    "搜索",
    "检索",
    "找一下",
}
SOFT_TASK_REQUEST_HINTS = {
    "请帮我",
    "帮我",
    "请你",
    "请",
    "帮忙",
    "please",
    "help me",
}
FREE_WORKFLOW_FILE_HINTS = {
    "pdf",
    "文档",
    "文件",
    "附件",
    "解析",
    "提取",
    "抽取",
    "转换",
    "ocr",
    "合并",
    "拆分",
    "格式化",
}
FREE_WORKFLOW_CONTENT_HINTS = {
    "进行中的任务",
    "在进行中的任务",
    "我的任务",
    "任务状态",
    "任务列表",
    "active task",
    "active tasks",
    "task status",
    "task list",
    "演讲",
    "演讲稿",
    "发言稿",
    "稿子",
    "文案",
    "宣传文案",
    "脚本",
    "改写",
    "润色",
    "rewrite",
    "polish",
    "speech",
    "copy",
    "copywriting",
}
PROFESSIONAL_SYSTEM_HINTS = {
    "crm",
    "erp",
    "oa",
    "sap",
    "salesforce",
    "业务系统",
    "客户系统",
    "订单系统",
    "审批系统",
    "财务系统",
    "hr系统",
    "人事系统",
    "内网系统",
    "数据库",
    "db",
    "sql",
}
PROFESSIONAL_ACTION_HINTS = {
    "获取",
    "查询",
    "拉取",
    "检索",
    "导出",
    "发送",
    "同步",
    "写入",
    "更新",
    "审批",
    "提交",
    "下单",
    "下订单",
    "下了",
    "订购",
    "购买",
    "成交",
    "推送",
    "fetch",
    "query",
    "export",
    "send",
    "sync",
    "update",
    "submit",
    "approve",
}
PROFESSIONAL_DATA_HINTS = {
    "订单",
    "客户",
    "合同",
    "财务",
    "发票",
    "库存",
    "销售",
    "回款",
    "报表",
    "业务数据",
    "数据记录",
    "order",
    "invoice",
    "customer",
    "contract",
    "business data",
}
PROFESSIONAL_AMBIGUOUS_DATA_HINTS = {
    "客户",
    "customer",
}
PROFESSIONAL_DELIVERY_NOTE_HINTS = {
    "送货单",
    "送货单号",
    "发货单",
    "delivery note",
    "delivery order",
    "已出路由",
}
PROFESSIONAL_DELIVERY_NOTE_ACTION_HINTS = {
    "导出",
    "pdf",
    "export",
    "发送给客户",
    "发给客户",
    "发送客户",
    "给客户",
    "send to customer",
}
PROFESSIONAL_SYSTEM_NAVIGATION_HINTS = {
    "登录",
    "网址",
    "页面",
    "列表",
    "路由",
    "http://",
    "https://",
}
PERMISSION_REQUIREMENT_HINTS = {
    "权限",
    "授权",
    "审批",
    "凭证",
    "token",
    "账号",
    "登录",
    "内部",
    "敏感",
    "admin",
    "operator",
    "viewer",
}
SCHEDULE_WEEKDAY_HINTS = {
    "每周一": 1,
    "每周二": 2,
    "每周三": 3,
    "每周四": 4,
    "每周五": 5,
    "每周六": 6,
    "每周日": 0,
    "每周天": 0,
    "every monday": 1,
    "every tuesday": 2,
    "every wednesday": 3,
    "every thursday": 4,
    "every friday": 5,
    "every saturday": 6,
    "every sunday": 0,
}
CAPABILITY_PRIORITY = (
    "permission_validation",
    "secure_tool_execution",
    "audit_logging",
    "enterprise_system_access",
    "crm_data_access",
    "order_data_access",
    "structured_data_query",
    "system_write_operation",
    "document_export",
    "notification_delivery",
    "task_status_lookup",
    "task_listing",
    "weather_lookup",
    "live_information_lookup",
    "web_search",
    "information_retrieval",
    "pdf_processing",
    "document_conversion",
    "content_generation",
    "speechwriting",
    "copywriting",
    "summarization",
    "translation",
)


def contains_any(text: str, keywords: set[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def normalize_text(text: str) -> str:
    return " ".join(str(text or "").strip().lower().split())


def normalize_intent(value: Any) -> str | None:
    normalized = str(value or "").strip().lower()
    if normalized in {"search", "write", "help"}:
        return normalized
    return None


def string_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    return [item for item in (str(value or "").strip().lower() for value in values) if item]


def classify_intent(text: str) -> dict[str, Any]:
    normalized_text = normalize_text(text)
    scores = {"search": 0, "write": 0, "help": 0}
    reasons: dict[str, list[str]] = {intent: [] for intent in scores}

    for intent, rules in INTENT_SIGNAL_RULES.items():
        for keyword, weight in rules:
            if keyword in normalized_text:
                scores[intent] += weight
                reasons[intent].append(keyword)

    if not any(scores.values()):
        scores["help"] = 1
        reasons["help"].append("default_help_fallback")

    ordered = sorted(scores.items(), key=lambda item: (item[1], item[0] == "help"), reverse=True)
    best_intent, best_score = ordered[0]
    total_score = sum(max(score, 0) for score in scores.values())
    confidence = round(best_score / max(total_score, 1), 3)

    return {
        "intent": best_intent,
        "scores": scores,
        "reasons": reasons,
        "confidence": confidence,
    }


def dispatch_intent(text: str) -> str:
    return str(classify_intent(text)["intent"])


def target_agent_name(intent: str) -> str:
    return {
        "search": "搜索 Agent",
        "write": "写作 Agent",
        "help": "写作 Agent",
    }[intent]


def is_direct_question(text: str) -> bool:
    normalized_text = normalize_text(text)
    if not normalized_text:
        return False
    return (
        "?" in normalized_text
        or "？" in normalized_text
        or contains_any(normalized_text, DIRECT_QUESTION_HINTS)
    )


def classify_interaction_mode(text: str, *, intent: str) -> str:
    normalized_text = normalize_text(text)
    if not normalized_text:
        return "chat"

    is_project_domain = contains_any(normalized_text, PROJECT_DOMAIN_HINTS)
    is_live_information_request = contains_any(normalized_text, LIVE_INFORMATION_HINTS)
    direct_question = is_direct_question(normalized_text)

    if len(normalized_text) <= 40 and (
        contains_any(normalized_text, CHAT_GREETING_HINTS)
        or contains_any(normalized_text, CHAT_SMALL_TALK_HINTS)
    ):
        return "chat"

    if len(normalized_text) <= 80 and contains_any(normalized_text, CHAT_FOLLOW_UP_HINTS):
        return "chat"

    if contains_any(normalized_text, CHAT_CLARIFICATION_HINTS):
        return "chat"

    if contains_any(normalized_text, HARD_TASK_REQUEST_HINTS):
        return "task"

    if direct_question and not is_project_domain:
        return "chat"

    if contains_any(normalized_text, SEARCH_TASK_HINTS):
        if is_live_information_request and not is_project_domain:
            return "chat"
        if direct_question and not is_project_domain:
            return "chat"
        return "task"

    if intent == "write" and not direct_question:
        return "task"

    if len(normalized_text) <= 48 and contains_any(normalized_text, SOFT_TASK_REQUEST_HINTS):
        return "chat"

    if contains_any(normalized_text, WORKFLOW_OR_DIRECT_HINTS):
        return "workflow_or_direct"

    if intent in {"search", "write"} and len(normalized_text) >= 36:
        return "task"

    if intent == "help" and len(normalized_text) <= 36:
        return "chat"

    return "workflow_or_direct"


def classify_reception_mode(text: str, *, intent: str, interaction_mode: str) -> str:
    normalized_text = normalize_text(text)
    if not normalized_text:
        return "welcome"

    is_live_information_request = contains_any(normalized_text, LIVE_INFORMATION_HINTS)
    is_project_domain = contains_any(normalized_text, PROJECT_DOMAIN_HINTS)

    if interaction_mode != "chat":
        return "task_handoff"

    if contains_any(normalized_text, CHAT_GREETING_HINTS):
        return "welcome"

    if contains_any(normalized_text, CHAT_FOLLOW_UP_HINTS):
        return "continuation"

    if contains_any(normalized_text, CHAT_SMALL_TALK_HINTS):
        return "small_talk"

    if contains_any(normalized_text, CHAT_CLARIFICATION_HINTS):
        return "clarify"

    if is_direct_question(normalized_text):
        return "direct_question"

    if is_live_information_request and not is_project_domain:
        return "direct_question"

    if len(normalized_text) <= 48 and contains_any(normalized_text, RECEPTION_CLARIFY_HINTS):
        return "clarify"

    if intent in {"search", "write"}:
        return "task_handoff"

    if len(normalized_text) <= 24:
        return "clarify"

    return "continuation"


def is_professional_workflow_request(normalized_text: str) -> bool:
    if not normalized_text:
        return False

    has_system = contains_any(normalized_text, PROFESSIONAL_SYSTEM_HINTS)
    has_action = contains_any(normalized_text, PROFESSIONAL_ACTION_HINTS)
    has_business_data = contains_any(normalized_text, PROFESSIONAL_DATA_HINTS)
    has_strict_business_data = contains_any(
        normalized_text,
        PROFESSIONAL_DATA_HINTS - PROFESSIONAL_AMBIGUOUS_DATA_HINTS,
    )
    has_permission_hint = contains_any(normalized_text, PERMISSION_REQUIREMENT_HINTS)
    is_delivery_note_export = (
        contains_any(normalized_text, PROFESSIONAL_DELIVERY_NOTE_HINTS)
        and contains_any(normalized_text, PROFESSIONAL_DELIVERY_NOTE_ACTION_HINTS)
        and contains_any(normalized_text, PROFESSIONAL_SYSTEM_NAVIGATION_HINTS)
    )

    if is_delivery_note_export:
        return True

    if has_system and (has_action or has_business_data or has_permission_hint):
        return True
    if has_strict_business_data and has_action:
        return True
    if has_permission_hint and has_strict_business_data and (has_action or has_system):
        return True
    return False


def classify_workflow_mode(text: str, *, intent: str, interaction_mode: str) -> str:
    normalized_text = normalize_text(text)
    if not normalized_text:
        return "chat"

    if is_professional_workflow_request(normalized_text):
        return "professional_workflow"

    if (
        contains_any(normalized_text, LIVE_INFORMATION_HINTS)
        or contains_any(normalized_text, FREE_WORKFLOW_FILE_HINTS)
        or contains_any(normalized_text, FREE_WORKFLOW_CONTENT_HINTS)
    ):
        return "free_workflow"

    if interaction_mode == "chat":
        if contains_any(
            normalized_text,
            CHAT_GREETING_HINTS | CHAT_SMALL_TALK_HINTS | CHAT_CLARIFICATION_HINTS,
        ):
            return "chat"
        if intent == "help" and is_direct_question(normalized_text):
            return "chat"

    if interaction_mode in {"task", "workflow_or_direct"}:
        return "free_workflow"
    if intent in {"search", "write"}:
        return "free_workflow"
    return "chat"


def classify_permission_requirement(text: str, *, workflow_mode: str) -> bool:
    if workflow_mode == "professional_workflow":
        return True

    normalized_text = normalize_text(text)
    if not normalized_text:
        return False

    has_permission_hint = contains_any(normalized_text, PERMISSION_REQUIREMENT_HINTS)
    has_enterprise_context = contains_any(
        normalized_text,
        PROFESSIONAL_SYSTEM_HINTS | PROFESSIONAL_DATA_HINTS,
    )
    return has_permission_hint and has_enterprise_context


def ordered_capabilities(capabilities: set[str]) -> list[str]:
    if not capabilities:
        return []
    prioritized = [item for item in CAPABILITY_PRIORITY if item in capabilities]
    remainder = sorted(capabilities - set(prioritized))
    return [*prioritized, *remainder]


def infer_required_capabilities(text: str, *, intent: str, workflow_mode: str) -> list[str]:
    normalized_text = normalize_text(text)
    if not normalized_text or workflow_mode == "chat":
        return []

    capabilities: set[str] = set()
    is_professional = workflow_mode == "professional_workflow"
    is_live_information_request = contains_any(normalized_text, LIVE_INFORMATION_HINTS)
    is_file_task = contains_any(normalized_text, FREE_WORKFLOW_FILE_HINTS)
    is_content_task = contains_any(normalized_text, FREE_WORKFLOW_CONTENT_HINTS)

    if is_professional:
        capabilities.update({"permission_validation", "secure_tool_execution", "audit_logging"})
        capabilities.add("enterprise_system_access")
        if contains_any(normalized_text, {"crm", "salesforce", "客户", "customer"}):
            capabilities.add("crm_data_access")
        if contains_any(normalized_text, {"订单", "order"}):
            capabilities.add("order_data_access")
        if contains_any(normalized_text, {"查询", "获取", "拉取", "检索", "query", "fetch"}):
            capabilities.add("structured_data_query")
        if contains_any(normalized_text, {"写入", "更新", "同步", "提交", "update", "sync", "submit"}):
            capabilities.add("system_write_operation")
        if contains_any(normalized_text, {"导出", "pdf", "export"}):
            capabilities.add("document_export")
        if contains_any(normalized_text, {"发送", "推送", "邮件", "通知", "send", "push", "email"}):
            capabilities.add("notification_delivery")
        return ordered_capabilities(capabilities)

    if is_live_information_request:
        capabilities.update({"live_information_lookup", "web_search"})
        if contains_any(normalized_text, {"天气", "气温", "温度", "weather", "forecast", "temperature"}):
            capabilities.add("weather_lookup")
    if contains_any(
        normalized_text,
        {"进行中的任务", "我的任务", "任务状态", "task status", "active task", "active tasks"},
    ):
        capabilities.add("task_status_lookup")
    if contains_any(normalized_text, {"任务列表", "最近任务", "task list"}):
        capabilities.add("task_listing")
    if is_file_task:
        capabilities.update({"pdf_processing", "document_conversion"})
    if is_content_task or intent in {"write", "help"}:
        capabilities.add("content_generation")
    if contains_any(normalized_text, {"演讲", "演讲稿", "发言稿", "speech"}):
        capabilities.add("speechwriting")
    if contains_any(normalized_text, {"文案", "copy", "copywriting"}):
        capabilities.add("copywriting")
    if intent == "search" or contains_any(normalized_text, SEARCH_TASK_HINTS):
        capabilities.add("information_retrieval")
    if contains_any(normalized_text, {"总结", "整理", "summarize"}):
        capabilities.add("summarization")
    if contains_any(normalized_text, {"翻译", "translate"}):
        capabilities.add("translation")

    return ordered_capabilities(capabilities)


def build_workflow_metadata(text: str, *, intent: str, interaction_mode: str) -> dict[str, Any]:
    workflow_mode = classify_workflow_mode(text, intent=intent, interaction_mode=interaction_mode)
    requires_permission = classify_permission_requirement(text, workflow_mode=workflow_mode)
    required_capabilities = infer_required_capabilities(
        text,
        intent=intent,
        workflow_mode=workflow_mode,
    )
    if requires_permission and "permission_validation" not in required_capabilities:
        required_capabilities = ["permission_validation", *required_capabilities]

    return {
        "workflow_mode": workflow_mode,
        "workflowMode": workflow_mode,
        "requires_permission": requires_permission,
        "requiresPermission": requires_permission,
        "required_capabilities": required_capabilities,
        "requiredCapabilities": required_capabilities,
    }


def parse_schedule_plan(text: str) -> dict[str, Any] | None:
    normalized_text = normalize_text(text)
    if not normalized_text:
        return None
    if "每周" not in normalized_text and "every " not in normalized_text:
        return None

    weekday: int | None = None
    for hint, value in SCHEDULE_WEEKDAY_HINTS.items():
        if hint in normalized_text:
            weekday = value
            break
    if weekday is None:
        return None

    hour = 9
    minute = 0
    if "下午" in normalized_text or "pm" in normalized_text:
        hour = 15
    if "晚上" in normalized_text:
        hour = 20
    if "上午" in normalized_text or "am" in normalized_text:
        hour = 9

    for h in range(0, 24):
        if f"{h}点" in normalized_text or f"{h}:00" in normalized_text:
            hour = h
            break
    for m in (0, 10, 15, 20, 30, 40, 45, 50):
        if f"{m}分" in normalized_text:
            minute = m
            break

    if ("下午" in normalized_text or "pm" in normalized_text) and hour < 12:
        hour += 12
    if ("上午" in normalized_text or "am" in normalized_text) and hour == 12:
        hour = 0

    cron = f"{minute} {hour} * * {weekday}"
    return {
        "kind": "weekly_report",
        "cron": cron,
        "timezone": "Asia/Shanghai",
        "summary": f"每周{['日', '一', '二', '三', '四', '五', '六'][weekday]} {hour:02d}:{minute:02d}",
        "source": "natural_language",
    }


def governance_metadata(text: str, *, workflow_mode: str) -> dict[str, Any]:
    normalized_text = normalize_text(text)
    schedule_plan = parse_schedule_plan(text)
    high_risk_write = workflow_mode == "professional_workflow" and contains_any(
        normalized_text,
        {"写入", "更新", "创建", "修改", "删除", "审批", "submit", "update", "create", "delete", "approve"},
    )
    confirmation_required = workflow_mode == "professional_workflow"
    confirmation_status = "pending" if confirmation_required else "not_required"
    confirmation_deadline = None
    if confirmation_required:
        confirmation_deadline = (datetime.now(UTC) + timedelta(minutes=30)).isoformat()

    return {
        "route_version": "r1.2",
        "confirmation_required": confirmation_required,
        "confirmation_status": confirmation_status,
        "confirmation_deadline_at": confirmation_deadline,
        "requires_approval": high_risk_write,
        "approval_required": high_risk_write,
        "approval_status": "pending" if high_risk_write else "not_required",
        "audit_id": f"audit-{uuid4().hex[:12]}",
        "idempotency_key": f"route:{uuid4().hex[:16]}",
        "execution_scope": "read_only" if not high_risk_write else "write_protected",
        "evidence_policy": "strict",
        "schedule_plan": schedule_plan,
    }


def workflow_mode_label(workflow_mode: str) -> str:
    return {
        "chat": "接待对话",
        "free_workflow": "自由工作流",
        "professional_workflow": "专业工作流",
    }.get(workflow_mode, "接待对话")


def enrich_route_decision_with_workflow_mode(
    route_decision: dict[str, Any],
    *,
    text: str,
    intent: str,
    interaction_mode: str,
    reception_mode: str,
) -> dict[str, Any]:
    workflow_metadata = build_workflow_metadata(
        text,
        intent=intent,
        interaction_mode=interaction_mode,
    )
    workflow_mode = str(workflow_metadata.get("workflow_mode") or "chat")
    user_visible_workflow_mode = workflow_mode_label(workflow_mode)
    governance = governance_metadata(text, workflow_mode=workflow_mode)

    route_decision.update(workflow_metadata)
    route_decision.update(governance)
    route_decision["routeVersion"] = route_decision.get("route_version")
    route_decision["confirmationRequired"] = route_decision.get("confirmation_required")
    route_decision["confirmationStatus"] = route_decision.get("confirmation_status")
    route_decision["confirmationDeadlineAt"] = route_decision.get("confirmation_deadline_at")
    route_decision["requiresApproval"] = route_decision.get("requires_approval")
    route_decision["approvalRequired"] = route_decision.get("approval_required")
    route_decision["approvalStatus"] = route_decision.get("approval_status")
    route_decision["auditId"] = route_decision.get("audit_id")
    route_decision["idempotencyKey"] = route_decision.get("idempotency_key")
    route_decision["executionScope"] = route_decision.get("execution_scope")
    route_decision["evidencePolicy"] = route_decision.get("evidence_policy")
    route_decision["schedulePlan"] = route_decision.get("schedule_plan")
    route_decision["user_visible_workflow_mode"] = user_visible_workflow_mode
    route_decision["userVisibleWorkflowMode"] = user_visible_workflow_mode
    return route_decision


def apply_interaction_mode_safety_correction(
    text: str,
    *,
    intent: str,
    interaction_mode: str,
    reception_mode: str,
) -> tuple[str, str]:
    workflow_mode = classify_workflow_mode(text, intent=intent, interaction_mode=interaction_mode)
    if workflow_mode == "professional_workflow" and interaction_mode == "chat":
        return "workflow_or_direct", "task_handoff"
    return interaction_mode, reception_mode
