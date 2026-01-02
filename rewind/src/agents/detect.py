from __future__ import annotations

import os
import re
from typing import Any, Mapping

from .jsonpath import get_path
from .types import AgentOverrides, AgentProfile


def _truthy_env(env: Mapping[str, str], key: str) -> bool:
    return bool(env.get(key, ""))


def score_profile(profile: AgentProfile, payload: Mapping[str, Any], env: Mapping[str, str]) -> int:
    detection = profile.data.get("detection") if isinstance(profile.data, dict) else None
    rules = detection.get("score_rules") if isinstance(detection, dict) else None
    if not isinstance(rules, list):
        return 0

    score = 0
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        when = rule.get("when")
        if not isinstance(when, dict):
            continue
        points = int(rule.get("score", 0) or 0)

        if "json_path_exists" in when:
            path = str(when.get("json_path_exists") or "")
            if path and get_path(payload, path) is not None:
                score += points
            continue

        if "json_path_matches" in when:
            spec = when.get("json_path_matches")
            if isinstance(spec, list) and len(spec) == 2:
                path, pattern = spec
                val = get_path(payload, str(path))
                if isinstance(val, str) and re.search(str(pattern), val):
                    score += points
            continue

        if "env_exists" in when:
            key = str(when.get("env_exists") or "")
            if key and _truthy_env(env, key):
                score += points
            continue

    return score


def min_score(profile: AgentProfile) -> int:
    detection = profile.data.get("detection") if isinstance(profile.data, dict) else None
    if not isinstance(detection, dict):
        return 0
    return int(detection.get("min_score", 0) or 0)


def select_profile(
    profiles: list[AgentProfile],
    *,
    overrides: AgentOverrides | None,
    payload: Mapping[str, Any],
    env: Mapping[str, str] | None = None,
) -> AgentProfile | None:
    env = env or os.environ
    if overrides and overrides.agent:
        wanted = overrides.agent.strip().lower()
        for p in profiles:
            if p.id.lower() == wanted:
                return p
        return None

    scored: list[tuple[int, AgentProfile]] = []
    for p in profiles:
        s = score_profile(p, payload, env)
        if s >= min_score(p):
            scored.append((s, p))

    if not scored:
        return None
    scored.sort(key=lambda t: (-t[0], t[1].id))
    return scored[0][1]
