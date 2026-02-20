"""OpenViking memory integration for cross-session agent memory."""

from skillkit.memory.client import OpenVikingClient
from skillkit.memory.config import MemoryConfig
from skillkit.memory.extension import setup_memory

__all__ = [
    "MemoryConfig",
    "OpenVikingClient",
    "setup_memory",
]
