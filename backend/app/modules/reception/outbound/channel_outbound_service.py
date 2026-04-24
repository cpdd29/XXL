from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from uuid import uuid4

from app.modules.reception.channel_ingress.dingtalk import encode_dingtalk_delivery_target
from app.modules.reception.channel_ingress.base import ChannelAdapter
from app.modules.reception.channel_ingress.registry import channel_adapter_registry
from app.modules.reception.schemas.messages import ChannelType, channel_display_name, normalize_channel_type
from app.platform.observability.operational_log_service import append_realtime_event
from app.platform.persistence.persistence_service import persistence_service
from app.platform.config.settings_service import get_channel_integration_runtime_settings
from app.platform.persistence.runtime_store import store
from app.platform.observability.trace_exporter_service import trace_exporter_service


TELEGRAM_MESSAGE_LIMIT = 3900
OUTBOUND_MAX_ATTEMPTS = 2

def _append_outbound_audit(
    *,
    task: dict,
    channel: str,
    action: str,
    status_value: str,
    details: str,
    delivered_target: str | None = None,
) -> None:
    trace_id = str(task.get("trace_id") or "").strip()
    metadata = None
    if trace_id:
        metadata = {
            "trace": {
                "trace_id": trace_id,
                "span_id": uuid4().hex[:16],
                "parent_span_id": None,
                "operation": "channel_outbound",
                "layer": "channel_outbound",
                "outcome": status_value,
                "status_code": 200 if status_value == "success" else 202 if status_value == "warning" else 500,
                "channel": channel or "unbound",
                "task_id": str(task.get("id") or ""),
                "workflow_run_id": str(task.get("workflow_run_id") or ""),
                "target_id": str(delivered_target or ""),
                "ended_at": datetime.now(UTC).isoformat(),
            }
        }

    payload = {
        "id": f"audit-outbound-{uuid4().hex[:10]}",
        "timestamp": store.now_string(),
        "action": action,
        "user": str(task.get("user_key") or task.get("session_id") or task.get("id") or "system"),
        "resource": f"channel_outbound:{channel or 'unbound'}",
        "status": status_value,
        "ip": "-",
        "details": details,
    }
    if metadata is not None:
        payload["metadata"] = metadata
    store.audit_logs.insert(0, store.clone(payload))
    del store.audit_logs[200:]
    persistence_service.append_audit_log(log=payload)
    trace_exporter_service.export_audit_event(payload)


class ChannelOutboundService:
    def __init__(
        self,
        *,
        adapters: Mapping[str | ChannelType, ChannelAdapter] | None = None,
    ) -> None:
        if adapters is None:
            self.adapters: dict[str, ChannelAdapter] = {
                channel.value: channel_adapter_registry.get(channel) for channel in ChannelType
            }
        else:
            self.adapters = {
                normalize_channel_type(channel).value: adapter for channel, adapter in adapters.items()
            }

    def render_task_result_text(self, task: dict, result: dict | None) -> str:
        return self._render_result_text(task, result)

    def render_task_failure_text(self, task: dict, error_message: str) -> str:
        title = str(task.get("title") or "").strip()
        if not title or title.startswith("渠道消息任务 -") or title == "任务执行失败":
            lead = "这次我没顺利处理完。"
        else:
            lead = f"关于“{title}”这件事，我这次没顺利处理完。"
        return self._truncate_text(
            "\n\n".join(
                [
                    lead,
                    error_message.strip() or "你可以稍后再试，或者补充更多背景，我继续帮你看。",
                ]
            )
        )

    def deliver_task_result(
        self,
        task: dict,
        result: dict | None,
        *,
        run: dict | None = None,
    ) -> dict[str, str]:
        channel = str(task.get("channel") or "").strip()
        if not channel:
            delivery = {
                "status": "skipped",
                "message": "结果已生成，当前任务未绑定出站渠道。",
            }
            _append_outbound_audit(
                task=task,
                channel="",
                action="渠道出站跳过",
                status_value="warning",
                details=delivery["message"],
            )
            return delivery

        return self._deliver_channel_message(
            task,
            channel=channel,
            text=self.render_task_result_text(task, result),
            run=run,
        )

    def deliver_task_failure(
        self,
        task: dict,
        error_message: str,
        *,
        run: dict | None = None,
    ) -> dict[str, str]:
        channel = str(task.get("channel") or "").strip()
        if not channel:
            delivery = {
                "status": "skipped",
                "message": "任务失败信息已记录，但当前任务未绑定可用出站渠道。",
            }
            _append_outbound_audit(
                task=task,
                channel="",
                action="渠道出站跳过",
                status_value="warning",
                details=delivery["message"],
            )
            return delivery
        return self._deliver_channel_message(
            task,
            channel=channel,
            text=self.render_task_failure_text(task, error_message),
            run=run,
        )

    def _deliver_channel_message(
        self,
        task: dict,
        *,
        channel: str,
        text: str,
        run: dict | None = None,
    ) -> dict[str, str]:
        adapter = self.adapters.get(channel)
        if adapter is None:
            delivery = {
                "status": "skipped",
                "message": f"结果已生成，当前暂不支持 {channel} 渠道回传。",
            }
            _append_outbound_audit(
                task=task,
                channel=channel,
                action="渠道出站跳过",
                status_value="warning",
                details=delivery["message"],
            )
            return delivery

        display_name = channel_display_name(channel)
        target_id = self._resolve_target_id(task, run=run, channel=channel)
        if not target_id:
            label = self._missing_target_label(channel=channel, run=run)
            message = f"结果已生成，但缺少 {display_name} {label}，无法自动回传。"
            append_realtime_event(
                agent=f"{display_name} Adapter",
                message=message,
                type_="warning",
                source="channel_outbound",
                trace_id=str(task.get("trace_id") or "").strip() or None,
                task_id=str(task.get("id") or "").strip() or None,
                workflow_run_id=str(task.get("workflow_run_id") or "").strip() or None,
                metadata={"event": "delivery_skipped_missing_target", "channel": channel},
            )
            delivery = {"status": "skipped", "message": message}
            _append_outbound_audit(
                task=task,
                channel=channel,
                action="渠道出站跳过",
                status_value="warning",
                details=message,
            )
            return delivery

        try:
            response = self._send_with_retry(adapter=adapter, chat_id=target_id, text=text)
        except NotImplementedError:
            message = f"结果已生成，但当前 {display_name} 渠道仅完成入站适配，暂未实现出站回传。"
            append_realtime_event(
                agent=f"{display_name} Adapter",
                message=message,
                type_="warning",
                source="channel_outbound",
                trace_id=str(task.get("trace_id") or "").strip() or None,
                task_id=str(task.get("id") or "").strip() or None,
                workflow_run_id=str(task.get("workflow_run_id") or "").strip() or None,
                metadata={
                    "event": "delivery_skipped_inbound_only",
                    "channel": channel,
                    "target_id": target_id,
                },
            )
            delivery = {"status": "skipped", "message": message}
            _append_outbound_audit(
                task=task,
                channel=channel,
                action="渠道出站跳过",
                status_value="warning",
                details=message,
                delivered_target=target_id,
            )
            return delivery
        except RuntimeError as exc:
            message = f"结果已生成，但 {display_name} 回传失败：{exc}"
            append_realtime_event(
                agent=f"{display_name} Adapter",
                message=message,
                type_="warning",
                source="channel_outbound",
                trace_id=str(task.get("trace_id") or "").strip() or None,
                task_id=str(task.get("id") or "").strip() or None,
                workflow_run_id=str(task.get("workflow_run_id") or "").strip() or None,
                metadata={
                    "event": "delivery_failed",
                    "channel": channel,
                    "target_id": target_id,
                    "error": str(exc),
                },
            )
            delivery = {"status": "failed", "message": message}
            _append_outbound_audit(
                task=task,
                channel=channel,
                action="渠道出站失败",
                status_value="error",
                details=message,
                delivered_target=target_id,
            )
            return delivery

        delivered_target = str(response.get("chat_id") or target_id)
        target_label = "chat" if channel == ChannelType.TELEGRAM.value else "会话"
        message = f"结果已通过 {display_name} 回传到 {target_label} {delivered_target}"
        append_realtime_event(
            agent=f"{display_name} Adapter",
            message=message,
            type_="success",
            source="channel_outbound",
            trace_id=str(task.get("trace_id") or "").strip() or None,
            task_id=str(task.get("id") or "").strip() or None,
            workflow_run_id=str(task.get("workflow_run_id") or "").strip() or None,
            metadata={
                "event": "delivery_succeeded",
                "channel": channel,
                "target_id": delivered_target,
            },
        )
        delivery = {"status": "sent", "message": message}
        _append_outbound_audit(
            task=task,
            channel=channel,
            action="渠道出站成功",
            status_value="success",
            details=message,
            delivered_target=delivered_target,
        )
        return delivery

    @staticmethod
    def _send_with_retry(
        *,
        adapter: ChannelAdapter,
        chat_id: str,
        text: str,
    ) -> dict[str, str]:
        last_error: RuntimeError | None = None
        for attempt in range(1, OUTBOUND_MAX_ATTEMPTS + 1):
            try:
                return adapter.send_message(chat_id=chat_id, text=text)
            except RuntimeError as exc:
                last_error = exc
                if attempt >= OUTBOUND_MAX_ATTEMPTS:
                    break
        if last_error is not None:
            raise last_error
        raise RuntimeError("Channel outbound delivery failed without adapter error")

    @staticmethod
    def _resolve_target_id(task: dict, *, run: dict | None, channel: str) -> str | None:
        dispatch_context = (run or {}).get("dispatch_context")
        channel_delivery = None
        if isinstance(dispatch_context, dict):
            candidate = dispatch_context.get("channel_delivery") or dispatch_context.get("channelDelivery")
            if isinstance(candidate, dict):
                channel_delivery = candidate

        if isinstance(channel_delivery, dict):
            binding_channel = str(channel_delivery.get("channel") or "").strip().lower()
            if binding_channel in {"", channel}:
                if channel == ChannelType.DINGTALK.value:
                    runtime_settings = get_channel_integration_runtime_settings()["dingtalk"]
                    platform_user_id = str(
                        channel_delivery.get("platform_user_id")
                        or channel_delivery.get("platformUserId")
                        or ""
                    ).strip()
                    corp_id = str(
                        channel_delivery.get("corp_id")
                        or channel_delivery.get("corpId")
                        or ""
                    ).strip()
                    session_webhook = str(
                        channel_delivery.get("session_webhook")
                        or channel_delivery.get("sessionWebhook")
                        or ""
                    ).strip()
                    conversation_id = str(
                        channel_delivery.get("conversation_id")
                        or channel_delivery.get("conversationId")
                        or ""
                    ).strip()
                    if (
                        platform_user_id
                        and str(runtime_settings.get("agent_id") or "").strip()
                        and str(runtime_settings.get("client_id") or "").strip()
                        and str(runtime_settings.get("client_secret") or "").strip()
                    ):
                        return encode_dingtalk_delivery_target(
                            {
                                "target_type": "openapi_user",
                                "platform_user_id": platform_user_id,
                                "corp_id": corp_id or None,
                                "conversation_id": conversation_id or None,
                                "session_webhook": session_webhook or None,
                            }
                        )
                    if session_webhook:
                        return session_webhook
                    target_type = str(channel_delivery.get("target_type") or "").strip().lower()
                    if target_type in {"session_webhook", "session_webhook_url"}:
                        target_id = str(channel_delivery.get("target_id") or "").strip()
                        if target_id:
                            return target_id
                    return None
                else:
                    target_id = str(channel_delivery.get("target_id") or "").strip()
                    if target_id:
                        return target_id

        session_id = str(task.get("session_id") or "").strip()
        if session_id:
            prefix = f"{channel}:"
            if session_id.startswith(prefix):
                chat_id = session_id[len(prefix) :].strip()
                return chat_id or None
            return session_id

        user_key = str(task.get("user_key") or "").strip()
        if user_key.startswith(f"{channel}:"):
            chat_id = user_key.split(":", maxsplit=1)[1].strip()
            return chat_id or None
        return None

    @staticmethod
    def _missing_target_label(*, channel: str, run: dict | None) -> str:
        if channel == ChannelType.TELEGRAM.value:
            return "chat_id"

        dispatch_context = (run or {}).get("dispatch_context")
        if isinstance(dispatch_context, dict):
            channel_delivery = dispatch_context.get("channel_delivery") or dispatch_context.get("channelDelivery")
            if isinstance(channel_delivery, dict) and channel == ChannelType.DINGTALK.value:
                platform_user_id = str(
                    channel_delivery.get("platform_user_id")
                    or channel_delivery.get("platformUserId")
                    or ""
                ).strip()
                if platform_user_id:
                    return "platformUserId / sessionWebhook"
                target_type = str(channel_delivery.get("target_type") or "").strip().lower()
                if target_type == "conversation_id":
                    return "sessionWebhook"
        return "会话标识"

    def _render_result_text(self, task: dict, result: dict | None) -> str:
        result = result or {}
        result_kind = str(result.get("kind") or "").strip().lower()
        if result_kind == "chat_reply":
            return self._truncate_text(
                self._render_chat_reply_text(
                    task=task,
                    result=result,
                )
            )

        title = str(result.get("title") or task.get("title") or "任务结果").strip()
        summary = str(result.get("summary") or "").strip()
        content = str(result.get("content") or "").strip()
        bullets = [
            str(item).strip()
            for item in result.get("bullets") or []
            if str(item).strip()
        ]
        references = [
            str(reference.get("title") or "").strip()
            for reference in result.get("references") or []
            if isinstance(reference, dict) and str(reference.get("title") or "").strip()
        ]

        parts = [f"【{title}】"]
        if summary:
            parts.append(summary)
        if content:
            parts.append(content)
        elif bullets:
            parts.append("\n".join(f"- {bullet}" for bullet in bullets[:5]))

        if references:
            parts.append(
                "参考资料：\n" + "\n".join(f"- {reference}" for reference in references[:3])
            )

        return self._truncate_text("\n\n".join(part for part in parts if part))

    @staticmethod
    def _render_chat_reply_text(*, task: dict, result: dict) -> str:
        for field in ("text", "content", "summary"):
            value = str(result.get(field) or "").strip()
            if value:
                return value

        bullets = [
            str(item).strip()
            for item in result.get("bullets") or []
            if str(item).strip()
        ]
        if bullets:
            return "\n".join(bullets[:3])

        fallback = str(task.get("title") or "").strip()
        return fallback or "收到，我继续处理。"

    @staticmethod
    def _truncate_text(text: str) -> str:
        if len(text) <= TELEGRAM_MESSAGE_LIMIT:
            return text
        suffix = "\n\n[内容较长，已截断显示]"
        return f"{text[: TELEGRAM_MESSAGE_LIMIT - len(suffix)]}{suffix}"


channel_outbound_service = ChannelOutboundService()
