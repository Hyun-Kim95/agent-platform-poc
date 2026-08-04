"""Settings and tenant YAML loading."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Literal, Optional

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]
TENANTS_DIR = ROOT / "configs" / "tenants"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    rules_only: bool = False
    web_search_provider: str = "tavily"
    web_search_api_key: str = ""
    run_store_path: str = "data/runs.db"  # SQLite fallback when Postgres down
    app_version: str = "0.1.0"

    # Observability (optional)
    langsmith_api_key: str = ""
    langsmith_tracing: bool = False
    langsmith_project: str = "agent-platform-poc"
    otel_enabled: bool = False
    otel_exporter: Literal["console", "none", "otlp"] = "console"
    otel_span_processor: Literal["simple", "batch"] = "simple"
    otel_exporter_endpoint: str = "http://127.0.0.1:4318/v1/traces"
    jsonl_log_path: str = "data/runs.jsonl"

    # Feedback (v0.2)
    feedback_log_path: str = "data/feedback.jsonl"  # JSONL fallback when Postgres down

    # Dev/test: force reviewer ok=False (loop smoke). Default off.
    force_reviewer_insufficient: bool = False

    # Token/cost lite: fill Meta.usage when engine omitted it
    usage_estimate_enabled: bool = True

    # Shared Postgres URL: pgvector docs + T2SQL sales + RunStore + Feedback
    # + LangGraph HITL checkpoints.
    # Empty URL => keyword RAG + SQLite T2SQL/RunStore + JSONL feedback
    # + SQLite checkpoints.
    vector_database_url: str = ""
    embedding_model: str = "text-embedding-3-small"

    # hybrid_rag Stretch S3: chunk / retrieve / rerank / collection
    rag_chunk_size: int = 0  # 0 = heading-only (legacy)
    rag_chunk_overlap: int = 64
    rag_top_k: int = 3
    rag_candidate_k: int = 12
    rag_rerank: bool = True
    rag_collection: str = ""  # empty = all collections

    # LangGraph HITL checkpointer (SQLite file when Postgres URL down)
    checkpoint_sqlite_path: str = "data/checkpoints.db"


class TenantConfig(BaseModel):
    tenant_id: str
    default_engine: str = "multi_agent"
    hitl: bool = False
    timeout_ms: int = 120_000
    max_iterations: int = 8
    rules_only: bool = False
    data_path: str = "samples/mini.csv"
    force_reviewer_insufficient: bool = False
    extra: Dict[str, Any] = Field(default_factory=dict)


@lru_cache
def get_settings() -> Settings:
    return Settings()


def load_tenant(tenant_id: str) -> Optional[TenantConfig]:
    path = TENANTS_DIR / f"{tenant_id}.yaml"
    if not path.is_file():
        return None
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    known = {
        "tenant_id",
        "default_engine",
        "hitl",
        "timeout_ms",
        "max_iterations",
        "rules_only",
        "data_path",
        "force_reviewer_insufficient",
    }
    extra = {k: v for k, v in raw.items() if k not in known}
    return TenantConfig(
        tenant_id=raw.get("tenant_id", tenant_id),
        default_engine=raw.get("default_engine", "multi_agent"),
        hitl=bool(raw.get("hitl", False)),
        timeout_ms=int(raw.get("timeout_ms", 120_000)),
        max_iterations=int(raw.get("max_iterations", 8)),
        rules_only=bool(raw.get("rules_only", False)),
        data_path=str(raw.get("data_path", "samples/mini.csv")),
        force_reviewer_insufficient=bool(
            raw.get("force_reviewer_insufficient", False)
        ),
        extra=extra,
    )
