from __future__ import annotations

from collections.abc import Mapping

from app.adapters.base import ChannelAdapter
from app.adapters.dingtalk import DingTalkAdapter
from app.adapters.feishu import FeishuAdapter
from app.adapters.telegram import TelegramAdapter
from app.adapters.wecom import WeComAdapter
from app.schemas.messages import ChannelType, normalize_channel_type


class ChannelAdapterRegistry:
    def __init__(self, adapters: Mapping[ChannelType | str, ChannelAdapter] | None = None) -> None:
        if adapters is None:
            adapters = {
                ChannelType.TELEGRAM: TelegramAdapter(),
                ChannelType.WECOM: WeComAdapter(),
                ChannelType.FEISHU: FeishuAdapter(),
                ChannelType.DINGTALK: DingTalkAdapter(),
            }

        self._adapters = {
            normalize_channel_type(channel): adapter for channel, adapter in adapters.items()
        }

    def get(self, channel: ChannelType | str) -> ChannelAdapter:
        normalized_channel = normalize_channel_type(channel)
        try:
            return self._adapters[normalized_channel]
        except KeyError as exc:
            raise ValueError(f"Unsupported channel: {normalized_channel.value}") from exc

    def has(self, channel: ChannelType | str) -> bool:
        normalized_channel = normalize_channel_type(channel)
        return normalized_channel in self._adapters


channel_adapter_registry = ChannelAdapterRegistry()
