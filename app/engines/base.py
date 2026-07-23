"""AgentEngine protocol."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.core.models import Envelope, EngineContext


@runtime_checkable
class AgentEngine(Protocol):
    name: str

    def run(self, ctx: EngineContext) -> Envelope:
        """Execute a new run. Must set meta.engine to self.name."""
        ...
