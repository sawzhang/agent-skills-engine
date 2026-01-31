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

from agent_skills_engine.config import SkillEntryConfig, SkillsConfig
from agent_skills_engine.engine import SkillsEngine
from agent_skills_engine.filters import DefaultSkillFilter, SkillFilter
from agent_skills_engine.loaders import MarkdownSkillLoader, SkillLoader
from agent_skills_engine.models import (
    Skill,
    SkillEntry,
    SkillInstallSpec,
    SkillInvocationPolicy,
    SkillMetadata,
    SkillRequirements,
    SkillSnapshot,
)
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
    # Config
    "SkillsConfig",
    "SkillEntryConfig",
    # Engine
    "SkillsEngine",
    # Loaders
    "SkillLoader",
    "MarkdownSkillLoader",
    # Filters
    "SkillFilter",
    "DefaultSkillFilter",
    # Runtime
    "SkillRuntime",
    "BashRuntime",
]
