"""
LLM provider adapters.

These adapters integrate the skills engine with different LLM providers,
making it easy to use skills in agent workflows.
"""

from agent_skills_engine.adapters.base import LLMAdapter

__all__ = ["LLMAdapter"]

# Optional imports for specific providers
try:
    from agent_skills_engine.adapters.openai import OpenAIAdapter  # noqa: F401

    __all__.append("OpenAIAdapter")
except ImportError:
    pass

try:
    from agent_skills_engine.adapters.anthropic import AnthropicAdapter  # noqa: F401

    __all__.append("AnthropicAdapter")
except ImportError:
    pass
