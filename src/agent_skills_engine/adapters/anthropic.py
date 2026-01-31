"""
Anthropic adapter for the skills engine.

Requires the 'anthropic' extra: pip install agent-skills-engine[anthropic]
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, TypedDict

try:
    from anthropic import AsyncAnthropic  # type: ignore[import-not-found]
except ImportError:
    raise ImportError(
        "Anthropic adapter requires the 'anthropic' package. "
        "Install with: pip install agent-skills-engine[anthropic]"
    )

from agent_skills_engine.adapters.base import AgentResponse, LLMAdapter, Message
from agent_skills_engine.engine import SkillsEngine


class AnthropicInputSchema(TypedDict):
    """Anthropic tool input schema."""

    type: str
    properties: dict[str, Any]
    required: list[str]


class AnthropicTool(TypedDict):
    """Anthropic tool definition."""

    name: str
    description: str
    input_schema: AnthropicInputSchema


class AnthropicMessage(TypedDict, total=False):
    """Anthropic message format."""

    role: str
    content: str | list[dict[str, Any]]


class AnthropicAdapter(LLMAdapter):
    """
    Anthropic adapter for the skills engine.

    Example:
        from anthropic import AsyncAnthropic
        from agent_skills_engine import SkillsEngine
        from agent_skills_engine.adapters import AnthropicAdapter

        engine = SkillsEngine(config=...)
        client = AsyncAnthropic()
        adapter = AnthropicAdapter(engine, client)

        response = await adapter.chat([
            Message(role="user", content="List my GitHub PRs")
        ])
    """

    def __init__(
        self,
        engine: SkillsEngine,
        client: AsyncAnthropic | None = None,
        model: str = "claude-3-5-sonnet-20241022",
        max_tokens: int = 4096,
        enable_tools: bool = True,
    ) -> None:
        super().__init__(engine)
        self.client = client or AsyncAnthropic()
        self.model = model
        self.max_tokens = max_tokens
        self.enable_tools = enable_tools

    def _get_anthropic_tools(self) -> list[AnthropicTool]:
        """Convert tool definitions to Anthropic format."""
        tool_defs = self.get_tool_definitions()
        return [
            {
                "name": tool["name"],
                "description": tool["description"],
                "input_schema": {
                    "type": tool["parameters"]["type"],
                    "properties": tool["parameters"]["properties"],
                    "required": tool["parameters"]["required"],
                },
            }
            for tool in tool_defs
        ]

    async def chat(
        self,
        messages: list[Message],
        system_prompt: str | None = None,
    ) -> AgentResponse:
        """Send a chat request to Anthropic."""
        # Build system prompt with skills
        full_system = self.build_system_prompt(system_prompt or "")

        # Format messages for Anthropic
        anthropic_messages: list[dict[str, Any]] = []

        for msg in messages:
            if msg.role == "system":
                # Anthropic handles system separately
                continue
            anthropic_messages.append(
                {
                    "role": msg.role,
                    "content": msg.content,
                }
            )

        # Build request kwargs
        request_kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": anthropic_messages,
        }

        if full_system:
            request_kwargs["system"] = full_system

        # Add tools if enabled
        if self.enable_tools:
            tools = self._get_anthropic_tools()
            if tools:
                request_kwargs["tools"] = tools

        # Call Anthropic
        response = await self.client.messages.create(**request_kwargs)

        # Extract content
        content = ""
        tool_calls = []

        for block in response.content:
            if block.type == "text":
                content += block.text
            elif block.type == "tool_use":
                tool_calls.append(
                    {
                        "id": block.id,
                        "name": block.name,
                        "arguments": block.input,
                    }
                )

        return AgentResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=response.stop_reason,
            usage={
                "prompt_tokens": response.usage.input_tokens,
                "completion_tokens": response.usage.output_tokens,
            },
        )

    async def chat_stream(
        self,
        messages: list[Message],
        system_prompt: str | None = None,
    ) -> AsyncIterator[str]:
        """Stream a chat response from Anthropic."""
        # Build system prompt with skills
        full_system = self.build_system_prompt(system_prompt or "")

        # Format messages for Anthropic
        anthropic_messages: list[dict[str, Any]] = []

        for msg in messages:
            if msg.role == "system":
                continue
            anthropic_messages.append(
                {
                    "role": msg.role,
                    "content": msg.content,
                }
            )

        # Stream from Anthropic
        async with self.client.messages.stream(
            model=self.model,
            max_tokens=self.max_tokens,
            system=full_system if full_system else None,
            messages=anthropic_messages,
        ) as stream:
            async for text in stream.text_stream:
                yield text
