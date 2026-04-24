from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.modules.agent_config.registries.brain_skill_service import brain_skill_service
from app.modules.agent_config.registries.mandatory_agent_registry_service import ensure_mandatory_agents_registered
from app.modules.dispatch.single_agent_runtime.agent_execution_worker_service import agent_execution_worker_service
from app.modules.dispatch.workflow_runtime.internal_event_delivery_poller_service import (
    internal_event_delivery_poller_service,
)
from app.modules.dispatch.workflow_runtime.workflow_dispatcher_service import workflow_dispatcher_service
from app.modules.dispatch.workflow_runtime.workflow_dispatch_poller_service import workflow_dispatch_poller_service
from app.modules.dispatch.workflow_runtime.workflow_execution_worker_service import workflow_execution_worker_service
from app.modules.dispatch.workflow_runtime.workflow_recovery_service import workflow_recovery_service
from app.modules.dispatch.workflow_runtime.mandatory_workflow_registry_service import ensure_mandatory_workflows_registered
from app.modules.organization.application.memory_service import memory_service
from app.modules.reception.application.message_ingestion_service import bootstrap_message_ingestion_state
from app.modules.reception.channel_ingress.dingtalk_stream_service import dingtalk_stream_service
from app.platform.messaging.nats_event_bus import nats_event_bus
from app.platform.messaging.redis_client import redis_provider
from app.platform.persistence.persistence_service import persistence_service
from app.router import api_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    _ = workflow_dispatcher_service
    _ = workflow_execution_worker_service
    _ = agent_execution_worker_service
    persistence_service.initialize()
    ensure_mandatory_workflows_registered()
    ensure_mandatory_agents_registered()
    brain_skill_service.bootstrap()
    bootstrap_message_ingestion_state()
    nats_event_bus.initialize()
    workflow_execution_worker_service.start()
    agent_execution_worker_service.start()
    workflow_recovery_service.bootstrap()
    workflow_dispatch_poller_service.start()
    internal_event_delivery_poller_service.start()
    dingtalk_stream_service.start()
    yield
    dingtalk_stream_service.stop()
    internal_event_delivery_poller_service.stop()
    workflow_dispatch_poller_service.stop()
    agent_execution_worker_service.stop()
    workflow_execution_worker_service.stop()
    memory_service.close()
    nats_event_bus.close()
    redis_provider.close()
    persistence_service.close()


settings = get_settings()
app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "environment": settings.environment}


app.include_router(api_router, prefix=settings.api_prefix)
