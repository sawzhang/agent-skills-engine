"""Package management for skills, extensions, themes, and prompts."""
from __future__ import annotations

from agent_skills_engine.packages.manager import PackageManager
from agent_skills_engine.packages.models import (
    PackageManifest,
    PathMetadata,
    ResolvedPackage,
    ResolvedResource,
)
from agent_skills_engine.packages.source import PackageSource, parse_source

__all__ = [
    "PackageManifest",
    "ResolvedPackage",
    "ResolvedResource",
    "PathMetadata",
    "PackageSource",
    "parse_source",
    "PackageManager",
]
