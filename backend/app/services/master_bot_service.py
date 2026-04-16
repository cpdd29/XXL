from __future__ import annotations

from typing import Any

from app.brain_core.routing.service import routing_service
from app.services.external_agent_registry_service import external_agent_registry_service
from app.services.external_skill_registry_service import external_skill_registry_service


"""Legacy compatibility facade for deprecated master_bot entrypoints.

Frozen contract:
- This module is not the primary production path.
- Do not add new business decisions or orchestration here.
- Keep behavior as thin delegation to current core services only.
"""


class MasterBotService:
    def route_message(
        self,
        *,
        text: str,
        channel: str | None = None,
        detected_lang: str | None = None,
    ) -> dict[str, Any]:
        return routing_service.route_message(
            text=text,
            channel=channel,
            detected_lang=detected_lang,
        )

    def list_external_capabilities(self) -> dict[str, Any]:
        return {
            "skills": external_skill_registry_service.list_skills(include_offline=True),
            "agents": external_agent_registry_service.list_agents(include_offline=True),
        }


master_bot_service = MasterBotService()

# Explicitly export only the compatibility facade entry.
__all__ = ["MasterBotService", "master_bot_service"]
