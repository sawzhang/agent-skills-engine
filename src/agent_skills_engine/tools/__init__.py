"""Built-in coding tools for the agent."""
from __future__ import annotations

from agent_skills_engine.tools.bash import BashTool
from agent_skills_engine.tools.edit import EditTool
from agent_skills_engine.tools.find import FindTool
from agent_skills_engine.tools.grep import GrepTool
from agent_skills_engine.tools.ls import LsTool
from agent_skills_engine.tools.read import ReadTool
from agent_skills_engine.tools.registry import ToolDefinition, ToolRegistry
from agent_skills_engine.tools.write import WriteTool

__all__ = [
    "ToolRegistry",
    "ToolDefinition",
    "ReadTool",
    "WriteTool",
    "EditTool",
    "BashTool",
    "GrepTool",
    "FindTool",
    "LsTool",
    "create_coding_tools",
    "create_all_tools",
    "create_read_only_tools",
]


def create_coding_tools(cwd: str | None = None) -> list[ToolDefinition]:
    """Create the standard coding tools (read, write, edit, bash)."""
    return [
        ReadTool(cwd).definition(),
        WriteTool(cwd).definition(),
        EditTool(cwd).definition(),
        BashTool(cwd).definition(),
    ]


def create_read_only_tools(cwd: str | None = None) -> list[ToolDefinition]:
    """Create read-only tools (read, grep, find, ls)."""
    return [
        ReadTool(cwd).definition(),
        GrepTool(cwd).definition(),
        FindTool(cwd).definition(),
        LsTool(cwd).definition(),
    ]


def create_all_tools(cwd: str | None = None) -> dict[str, ToolDefinition]:
    """Create all built-in tools as a name->definition dict."""
    tools = [
        ReadTool(cwd),
        WriteTool(cwd),
        EditTool(cwd),
        BashTool(cwd),
        GrepTool(cwd),
        FindTool(cwd),
        LsTool(cwd),
    ]
    return {t.name: t.definition() for t in tools}
