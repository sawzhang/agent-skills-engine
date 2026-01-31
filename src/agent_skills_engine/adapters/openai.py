"""
OpenAI adapter for the skills engine.

Requires the 'openai' extra: pip install agent-skills-engine[openai]
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, TypedDict

try:
    from openai import AsyncOpenAI  # type: ignore[import-not-found]
except ImportError:
    raise ImportError(
        "OpenAI adapter requires the 'openai' package. "
        "Install with: pip install agent-skills-engine[openai]"
    )

from agent_skills_engine.adapters.base import AgentResponse, LLMAdapter, Message
from agent_skills_engine.engine import SkillsEngine


class OpenAIFunction(TypedDict):
    """OpenAI function definition."""

    name: str
    description: str
    parameters: dict[str, Any]


class OpenAITool(TypedDict):
    """OpenAI tool definition."""

    type: str
    function: OpenAIFunction


class OpenAIMessage(TypedDict, total=False):
    """OpenAI message format."""

    role: str
    content: str | None
    tool_calls: list[dict[str, Any]]
    tool_call_id: str


class OpenAIAdapter(LLMAdapter):
    """
    OpenAI adapter for the skills engine.

    Example:
        from openai import AsyncOpenAI
        from agent_skills_engine import SkillsEngine
        from agent_skills_engine.adapters import OpenAIAdapter

        engine = SkillsEngine(config=...)
        client = AsyncOpenAI()
        adapter = OpenAIAdapter(engine, client)

        response = await adapter.chat([
            Message(role="user", content="List my GitHub PRs")
        ])
    """

    def __init__(
        self,
        engine: SkillsEngine,
        client: AsyncOpenAI | None = None,
        model: str = "gpt-4-turbo-preview",
        enable_tools: bool = True,
    ) -> None:
        super().__init__(engine)
        self.client = client or AsyncOpenAI()
        self.model = model
        self.enable_tools = enable_tools

    def _get_openai_tools(self) -> list[OpenAITool]:
        """Convert tool definitions to OpenAI format."""
        tool_defs = self.get_tool_definitions()
        return [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["parameters"],
                },
            }
            for tool in tool_defs
        ]

    async def chat(
        self,
        messages: list[Message],
        system_prompt: str | None = None,
    ) -> AgentResponse:
        """Send a chat request to OpenAI."""
        # Build system prompt with skills
        full_system = self.build_system_prompt(system_prompt or "")

        # Format messages for OpenAI
        openai_messages: list[dict[str, Any]] = []

        if full_system:
            openai_messages.append(
                {
                    "role": "system",
                    "content": full_system,
                }
            )

        for msg in messages:
            openai_messages.append(
                {
                    "role": msg.role,
                    "content": msg.content,
                }
            )

        # Build request kwargs
        request_kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": openai_messages,
        }

        # Add tools if enabled
        if self.enable_tools:
            tools = self._get_openai_tools()
            if tools:
                request_kwargs["tools"] = tools

        # Call OpenAI
        response = await self.client.chat.completions.create(**request_kwargs)

        choice = response.choices[0]
        content = choice.message.content or ""

        # Extract tool calls if any
        tool_calls = []
        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                tool_calls.append(
                    {
                        "id": tc.id,
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    }
                )

        return AgentResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason,
            usage={
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
            },
        )

    async def chat_stream(
        self,
        messages: list[Message],
        system_prompt: str | None = None,
    ) -> AsyncIterator[str]:
        """Stream a chat response from OpenAI."""
        # Build system prompt with skills
        full_system = self.build_system_prompt(system_prompt or "")

        # Format messages for OpenAI
        openai_messages: list[dict[str, Any]] = []

        if full_system:
            openai_messages.append(
                {
                    "role": "system",
                    "content": full_system,
                }
            )

        for msg in messages:
            openai_messages.append(
                {
                    "role": msg.role,
                    "content": msg.content,
                }
            )

        # Stream from OpenAI
        stream = await self.client.chat.completions.create(
            model=self.model,
            messages=openai_messages,
            stream=True,
        )

        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
