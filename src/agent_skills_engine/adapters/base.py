"""
Base LLM adapter interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, TypedDict

from agent_skills_engine.engine import SkillsEngine
from agent_skills_engine.models import SkillSnapshot


class ToolParameter(TypedDict, total=False):
    """Tool parameter definition."""

    type: str
    description: str
    enum: list[str]


class ToolProperties(TypedDict):
    """Tool properties schema."""

    type: str
    properties: dict[str, ToolParameter]
    required: list[str]


class ToolDefinition(TypedDict):
    """Standard tool definition format."""

    name: str
    description: str
    parameters: dict[str, Any]  # JSON schema for parameters


@dataclass
class Message:
    """A message in a conversation."""

    role: str  # "user", "assistant", "system"
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResponse:
    """Response from an agent."""

    content: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    finish_reason: str | None = None
    usage: dict[str, int] = field(default_factory=dict)


class LLMAdapter(ABC):
    """
    Abstract base class for LLM provider adapters.

    Adapters integrate the skills engine with specific LLM providers,
    handling system prompt injection, tool execution, and response parsing.

    Example implementation for a custom provider:

        class MyLLMAdapter(LLMAdapter):
            def __init__(self, engine: SkillsEngine, client: MyLLMClient):
                super().__init__(engine)
                self.client = client

            async def chat(self, messages: list[Message]) -> AgentResponse:
                # Inject skills into system prompt
                system_prompt = self.build_system_prompt()

                # Call LLM
                response = await self.client.chat(
                    system=system_prompt,
                    messages=[{"role": m.role, "content": m.content} for m in messages],
                )

                return AgentResponse(
                    content=response.content,
                    tool_calls=response.tool_calls,
                )
    """

    def __init__(self, engine: SkillsEngine) -> None:
        self.engine = engine

    def get_snapshot(self) -> SkillSnapshot:
        """Get the current skills snapshot."""
        return self.engine.get_snapshot()

    def build_system_prompt(self, base_prompt: str = "") -> str:
        """
        Build a system prompt with skills injected.

        Args:
            base_prompt: Base system prompt to extend

        Returns:
            System prompt with skills appended
        """
        snapshot = self.get_snapshot()
        skills_prompt = snapshot.prompt

        if not skills_prompt:
            return base_prompt

        if base_prompt:
            return f"{base_prompt}\n\n{skills_prompt}"
        return skills_prompt

    def get_tool_definitions(self) -> list[ToolDefinition]:
        """
        Get standard tool definitions for LLM function calling.

        Returns a list of tools that can be used with OpenAI, Anthropic, or
        other LLM providers that support function calling.

        Returns:
            List of tool definitions
        """
        return [
            {
                "name": "execute",
                "description": "Execute a single shell command and return the output.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "The shell command to execute",
                        },
                    },
                    "required": ["command"],
                },
            },
            {
                "name": "execute_script",
                "description": "Execute a multi-line shell script and return the output.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "script": {
                            "type": "string",
                            "description": "The shell script content to execute",
                        },
                    },
                    "required": ["script"],
                },
            },
        ]

    @abstractmethod
    async def chat(
        self,
        messages: list[Message],
        system_prompt: str | None = None,
    ) -> AgentResponse:
        """
        Send a chat request to the LLM.

        Args:
            messages: Conversation messages
            system_prompt: Optional system prompt (skills will be appended)

        Returns:
            AgentResponse with LLM output
        """
        pass

    async def chat_stream(
        self,
        messages: list[Message],
        system_prompt: str | None = None,
    ) -> AsyncIterator[str]:
        """
        Stream a chat response from the LLM.

        Default implementation falls back to non-streaming chat.
        Override for true streaming support.

        Args:
            messages: Conversation messages
            system_prompt: Optional system prompt

        Yields:
            Response chunks
        """
        response = await self.chat(messages, system_prompt)
        yield response.content

    async def run_agent_loop(
        self,
        messages: list[Message],
        system_prompt: str | None = None,
        max_turns: int = 10,
    ) -> list[Message]:
        """
        Run an agent loop with tool execution.

        Continues until the LLM stops requesting tools or max_turns is reached.

        Args:
            messages: Initial messages
            system_prompt: System prompt
            max_turns: Maximum number of turns

        Returns:
            Complete conversation including tool results
        """
        conversation = list(messages)

        for _ in range(max_turns):
            response = await self.chat(conversation, system_prompt)

            # Add assistant response
            conversation.append(
                Message(
                    role="assistant",
                    content=response.content,
                )
            )

            # Check for tool calls
            if not response.tool_calls:
                break

            # Execute tools and add results
            for tool_call in response.tool_calls:
                result = await self._execute_tool(tool_call)
                conversation.append(
                    Message(
                        role="tool",
                        content=result,
                        metadata={"tool_call_id": tool_call.get("id")},
                    )
                )

        return conversation

    async def _execute_tool(self, tool_call: dict[str, Any]) -> str:
        """Execute a tool call."""
        name = tool_call.get("name", "")
        args = tool_call.get("arguments", {})

        if name == "bash" or name == "execute":
            command = args.get("command", "")
            result = await self.engine.execute(command)
            if result.success:
                return result.output
            return f"Error: {result.error}"

        if name == "execute_script":
            script = args.get("script", "")
            result = await self.engine.execute_script(script)
            if result.success:
                return result.output
            return f"Error: {result.error}"

        return f"Unknown tool: {name}"
