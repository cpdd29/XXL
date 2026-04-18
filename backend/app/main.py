from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.config import get_settings
from app.core.nats_event_bus import nats_event_bus
from app.core.redis_client import redis_provider
from app.services.message_ingestion_service import bootstrap_message_ingestion_state
from app.services.agent_execution_worker_service import agent_execution_worker_service
from app.services.internal_event_delivery_poller_service import (
    internal_event_delivery_poller_service,
)
from app.services.workflow_dispatcher_service import workflow_dispatcher_service
from app.services.workflow_dispatch_poller_service import workflow_dispatch_poller_service
from app.services.workflow_execution_worker_service import workflow_execution_worker_service
from app.services.workflow_recovery_service import workflow_recovery_service
from app.services.memory_service import memory_service
from app.services.brain_skill_service import brain_skill_service
from app.services.mandatory_agent_registry_service import ensure_mandatory_agents_registered
from app.services.mandatory_workflow_registry_service import ensure_mandatory_workflows_registered
from app.services.persistence_service import persistence_service
from app.services.dingtalk_stream_service import dingtalk_stream_service


@asynccontextmanager
async def lifespan(_: FastAPI):
    _ = workflow_dispatcher_service
    _ = workflow_execution_worker_service
    _ = agent_execution_worker_service
    persistence_service.initialize()
    brain_skill_service.bootstrap()
    ensure_mandatory_agents_registered()
    ensure_mandatory_workflows_registered()
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
