"""
Extension system for the skillkit.

Provides a plugin-based architecture for registering custom tools,
commands, and event hooks.
"""

from skillkit.extensions.api import ExtensionAPI
from skillkit.extensions.manager import ExtensionManager
from skillkit.extensions.models import (
    COMMAND_INVOKED,
    SESSION_END,
    SESSION_START,
    SKILL_INVOKED,
    SKILL_LOADED,
    SNAPSHOT_CREATED,
    TOOL_CALL,
    TOOL_RESULT,
    CommandInfo,
    ExtensionHook,
    ExtensionInfo,
    ToolInfo,
)

__all__ = [
    "ExtensionAPI",
    "ExtensionManager",
    "ExtensionInfo",
    "ExtensionHook",
    "CommandInfo",
    "ToolInfo",
    "SESSION_START",
    "SESSION_END",
    "SKILL_LOADED",
    "SKILL_INVOKED",
    "TOOL_CALL",
    "TOOL_RESULT",
    "COMMAND_INVOKED",
    "SNAPSHOT_CREATED",
]
