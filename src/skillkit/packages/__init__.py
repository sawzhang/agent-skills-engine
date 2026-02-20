"""Package management for skills, extensions, themes, and prompts."""
from __future__ import annotations

from skillkit.packages.manager import PackageManager
from skillkit.packages.models import (
    PackageManifest,
    PathMetadata,
    ResolvedPackage,
    ResolvedResource,
)
from skillkit.packages.source import PackageSource, parse_source

__all__ = [
    "PackageManifest",
    "ResolvedPackage",
    "ResolvedResource",
    "PathMetadata",
    "PackageSource",
    "parse_source",
    "PackageManager",
]
