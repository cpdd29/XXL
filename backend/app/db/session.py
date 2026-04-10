from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


def create_engine_for_url(database_url: str) -> Engine:
    if database_url.startswith("sqlite"):
        engine_kwargs: dict[str, object] = {
            "future": True,
            "connect_args": {"check_same_thread": False},
        }
        if ":memory:" in database_url:
            engine_kwargs["poolclass"] = StaticPool
        return create_engine(database_url, **engine_kwargs)

    return create_engine(database_url, future=True, pool_pre_ping=True)


def create_session_factory(engine: Engine) -> sessionmaker:
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
