"""Simple engine registry (dict)."""

from __future__ import annotations

from typing import Dict, List, Optional

from app.engines.base import AgentEngine
from app.engines.echo import EchoEngine
from app.engines.multi_agent import MultiAgentEngine


class EngineRegistry:
    def __init__(self) -> None:
        self._engines: Dict[str, AgentEngine] = {}

    def register(self, engine: AgentEngine) -> None:
        self._engines[engine.name] = engine

    def get(self, name: str) -> Optional[AgentEngine]:
        return self._engines.get(name)

    def names(self) -> List[str]:
        return sorted(self._engines)


def build_default_registry() -> EngineRegistry:
    reg = EngineRegistry()
    reg.register(EchoEngine())
    reg.register(MultiAgentEngine())
    return reg
