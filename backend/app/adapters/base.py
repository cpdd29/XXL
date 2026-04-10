from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.schemas.messages import UnifiedMessage


class ChannelAdapter(ABC):
    def parse(self, payload: dict[str, Any]) -> UnifiedMessage:
        return self.receive_message(payload)

    @abstractmethod
    def receive_message(self, payload: dict[str, Any]) -> UnifiedMessage:
        """Convert a channel-native payload into a UnifiedMessage."""

    @abstractmethod
    def send_message(self, *, chat_id: str, text: str) -> dict[str, Any]:
        """Deliver a message to the channel."""

    @abstractmethod
    def get_user_info(self, platform_user_id: str) -> dict[str, Any]:
        """Resolve channel-native user metadata when needed."""
