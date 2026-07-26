"""AgentEngine protocol."""

from __future__ import annotations

from typing import Any, Dict, Optional, Protocol, runtime_checkable

from app.core.models import Envelope, EngineContext


@runtime_checkable
class AgentEngine(Protocol):
    name: str

    def run(self, ctx: EngineContext) -> Envelope:
        """Execute a new run. Must set meta.engine to self.name."""
        ...


@runtime_checkable
class ResumableEngine(Protocol):
    """Engines that support HITL resume after waiting_human."""

    name: str

    def run(self, ctx: EngineContext) -> Any:
        """May return Envelope or (Envelope, agent_state)."""
        ...

    def resume(
        self,
        ctx: EngineContext,
        agent_state: Dict[str, Any],
        decision: str,
        feedback: Optional[str] = None,
        revise_target: Optional[str] = None,
    ) -> Any:
        """May return Envelope or (Envelope, agent_state)."""
        ...
