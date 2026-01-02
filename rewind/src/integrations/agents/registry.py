from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Iterable

from ...utils.resources import resource_dir

from .types import AgentProfile


@dataclass(frozen=True, slots=True)
class AgentRegistry:
    profiles: tuple[AgentProfile, ...]

    @classmethod
    def load_bundled(cls) -> AgentRegistry:
        pkg = resource_dir("schemas", "agents")
        profiles: list[AgentProfile] = []
        for entry in sorted(pkg.iterdir(), key=lambda p: p.name):
            if entry.suffix != ".json":
                continue
            data = json.loads(entry.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                continue
            profile_id = str(data.get("id") or "").strip()
            if not profile_id:
                continue
            profiles.append(
                AgentProfile(
                    id=profile_id,
                    display_name=str(data.get("display_name") or profile_id),
                    data=data,
                )
            )

        return cls(profiles=tuple(profiles))

    def get(self, agent_id: str) -> AgentProfile | None:
        wanted = (agent_id or "").strip().lower()
        for p in self.profiles:
            if p.id.lower() == wanted:
                return p
        return None

    def all(self) -> Iterable[AgentProfile]:
        return self.profiles
