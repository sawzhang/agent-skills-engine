"""
Agent Skills Engine - A standalone skills execution engine for LLM agents.

This library provides a framework for defining, loading, filtering, and executing
skills in LLM-based agent systems. It is designed to be framework-agnostic and
can be integrated with any LLM provider (OpenAI, Anthropic, etc.).

Example:
    from agent_skills_engine import SkillsEngine, SkillsConfig

    # Initialize engine
    engine = SkillsEngine(
        config=SkillsConfig(
            skill_dirs=["./skills", "~/.agent/skills"],
            watch=True,
        )
    )

    # Load and filter skills
    skills = engine.load_skills()
    eligible = engine.filter_skills(skills)

    # Generate prompt for LLM
    prompt = engine.format_prompt(eligible)

    # Execute a skill
    result = await engine.execute("github", args={"action": "list-prs"})
"""

from agent_skills_engine.adapters.registry import AdapterFactory, AdapterRegistry
from agent_skills_engine.agent import (
    AgentAbortedError,
    AgentConfig,
    AgentMessage,
    AgentRunner,
    create_agent,
)
from agent_skills_engine.commands import CommandRegistry, CommandResult
from agent_skills_engine.context import (
    ContextCompactor,
    ContextManager,
    SlidingWindowCompactor,
    TokenBudgetCompactor,
    estimate_message_tokens,
    estimate_messages_tokens,
    estimate_tokens,
)
from agent_skills_engine.events import (
    AGENT_END,
    AGENT_START,
    AFTER_TOOL_RESULT,
    BEFORE_TOOL_CALL,
    CONTEXT_TRANSFORM,
    INPUT,
    TOOL_EXECUTION_UPDATE,
    TURN_END,
    TURN_START,
    AfterToolResultEvent,
    AgentEndEvent,
    AgentStartEvent,
    BeforeToolCallEvent,
    ContextTransformEvent,
    ContextTransformEventResult,
    EventBus,
    InputEvent,
    InputEventResult,
    StreamEvent,
    ToolCallEventResult,
    ToolExecutionUpdateEvent,
    ToolResultEventResult,
    TurnEndEvent,
    TurnStartEvent,
)
from agent_skills_engine.config import SkillEntryConfig, SkillsConfig
from agent_skills_engine.engine import SkillsEngine
from agent_skills_engine.extensions import (
    CommandInfo,
    ExtensionAPI,
    ExtensionInfo,
    ExtensionManager,
    ToolInfo,
)
from agent_skills_engine.filters import DefaultSkillFilter, SkillFilter
from agent_skills_engine.model_registry import (
    CostBreakdown,
    ModelCost,
    ModelDefinition,
    ModelRegistry,
    TokenUsage,
)
from agent_skills_engine.loaders import MarkdownSkillLoader, SkillLoader
from agent_skills_engine.models import (
    Skill,
    SkillAction,
    SkillActionParam,
    SkillEntry,
    SkillInstallSpec,
    SkillInvocationPolicy,
    SkillMetadata,
    SkillRequirements,
    SkillSnapshot,
)
from agent_skills_engine.prompts import PromptTemplate, PromptTemplateLoader
from agent_skills_engine.runtime import BashRuntime, SkillRuntime

__version__ = "0.1.0"

__all__ = [
    # Core models
    "Skill",
    "SkillMetadata",
    "SkillRequirements",
    "SkillSnapshot",
    "SkillEntry",
    "SkillInvocationPolicy",
    "SkillInstallSpec",
    "SkillAction",
    "SkillActionParam",
    # Config
    "SkillsConfig",
    "SkillEntryConfig",
    # Engine
    "SkillsEngine",
    # Agent
    "AgentRunner",
    "AgentConfig",
    "AgentMessage",
    "AgentAbortedError",
    "create_agent",
    # Events
    "EventBus",
    "AGENT_START",
    "AGENT_END",
    "TURN_START",
    "TURN_END",
    "BEFORE_TOOL_CALL",
    "AFTER_TOOL_RESULT",
    "CONTEXT_TRANSFORM",
    "INPUT",
    "TOOL_EXECUTION_UPDATE",
    "ToolExecutionUpdateEvent",
    "AgentStartEvent",
    "AgentEndEvent",
    "TurnStartEvent",
    "TurnEndEvent",
    "BeforeToolCallEvent",
    "ToolCallEventResult",
    "AfterToolResultEvent",
    "ToolResultEventResult",
    "ContextTransformEvent",
    "ContextTransformEventResult",
    "InputEvent",
    "InputEventResult",
    "StreamEvent",
    # Model Registry
    "ModelDefinition",
    "ModelCost",
    "ModelRegistry",
    "TokenUsage",
    "CostBreakdown",
    # Context Management
    "ContextManager",
    "ContextCompactor",
    "TokenBudgetCompactor",
    "SlidingWindowCompactor",
    "estimate_tokens",
    "estimate_message_tokens",
    "estimate_messages_tokens",
    # Loaders
    "SkillLoader",
    "MarkdownSkillLoader",
    # Filters
    "SkillFilter",
    "DefaultSkillFilter",
    # Runtime
    "SkillRuntime",
    "BashRuntime",
    # Adapters
    "AdapterRegistry",
    "AdapterFactory",
    # Extensions
    "ExtensionAPI",
    "ExtensionManager",
    "ExtensionInfo",
    "CommandInfo",
    "ToolInfo",
    # Commands
    "CommandRegistry",
    "CommandResult",
    # Prompts
    "PromptTemplate",
    "PromptTemplateLoader",
]
