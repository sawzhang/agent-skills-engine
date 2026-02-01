"""
Agent runner with automatic skill loading and execution.

Provides a Claude Code-like experience with:
- Automatic skill discovery and loading
- System prompt injection
- User-invocable skills (slash commands)
- Agent loop with tool execution
- File watching for hot-reload
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from agent_skills_engine.config import SkillsConfig

# Auto-load .env file from current directory or parent directories
load_dotenv()
from agent_skills_engine.engine import SkillsEngine
from agent_skills_engine.logging import get_logger
from agent_skills_engine.models import Skill, SkillSnapshot

logger = get_logger("agent")


@dataclass
class AgentMessage:
    """A message in the agent conversation."""

    role: str  # "user", "assistant", "system", "tool"
    content: str
    name: str | None = None  # For tool messages
    tool_call_id: str | None = None  # For tool results
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    reasoning: str | None = None  # For models with reasoning (MiniMax)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentConfig:
    """Configuration for the agent runner."""

    # LLM settings
    model: str = "MiniMax-M2.1"
    base_url: str | None = None  # Defaults to OPENAI_BASE_URL
    api_key: str | None = None  # Defaults to OPENAI_API_KEY
    temperature: float = 1.0
    max_tokens: int = 4096

    # Agent behavior
    max_turns: int = 20  # Max tool execution turns
    enable_tools: bool = True  # Enable function calling
    enable_reasoning: bool = True  # Enable reasoning_split for MiniMax
    auto_execute: bool = True  # Auto-execute tool calls

    # Skills settings
    skill_dirs: list[Path] = field(default_factory=list)
    watch_skills: bool = False  # Watch for skill file changes
    system_prompt: str = ""  # Base system prompt

    @classmethod
    def from_env(cls, **overrides: Any) -> AgentConfig:
        """Create config from environment variables."""
        return cls(
            base_url=os.environ.get("OPENAI_BASE_URL"),
            api_key=os.environ.get("OPENAI_API_KEY"),
            model=os.environ.get("MINIMAX_MODEL", "MiniMax-M2.1"),
            **overrides,
        )


class AgentRunner:
    """
    Agent runner with automatic skill loading.

    Example:
        # Quick start
        agent = AgentRunner.create(
            skill_dirs=[Path("./skills")],
            system_prompt="You are a helpful assistant."
        )

        # Chat
        response = await agent.chat("Help me create a PDF")
        print(response.content)

        # Or run interactive loop
        await agent.run_interactive()
    """

    def __init__(
        self,
        engine: SkillsEngine,
        config: AgentConfig | None = None,
    ) -> None:
        self.engine = engine
        self.config = config or AgentConfig.from_env()
        self._client: Any = None
        self._conversation: list[AgentMessage] = []
        self._on_skill_change: list[Callable[[set[Path]], None]] = []

    @classmethod
    def create(
        cls,
        skill_dirs: list[Path] | None = None,
        system_prompt: str = "",
        **config_kwargs: Any,
    ) -> AgentRunner:
        """
        Create an agent runner with automatic skill loading.

        Args:
            skill_dirs: Directories to load skills from
            system_prompt: Base system prompt
            **config_kwargs: Additional AgentConfig parameters

        Returns:
            Configured AgentRunner instance
        """
        # Build skills config
        skills_config = SkillsConfig(
            skill_dirs=skill_dirs or [],
            watch=config_kwargs.get("watch_skills", False),
        )

        # Create engine
        engine = SkillsEngine(config=skills_config)

        # Build agent config
        agent_config = AgentConfig.from_env(
            skill_dirs=skill_dirs or [],
            system_prompt=system_prompt,
            **config_kwargs,
        )

        return cls(engine, agent_config)

    @property
    def client(self) -> Any:
        """Get or create the OpenAI client."""
        if self._client is None:
            try:
                from openai import AsyncOpenAI
                import httpx
            except ImportError:
                raise ImportError(
                    "AgentRunner requires the 'openai' package. "
                    "Install with: pip install openai"
                )

            # Create httpx client without proxy to avoid SOCKS proxy issues
            # trust_env=False prevents reading proxy settings from environment
            http_client = httpx.AsyncClient(
                trust_env=False,
                timeout=httpx.Timeout(300.0, connect=30.0),  # 5 min timeout for complex tasks
            )

            self._client = AsyncOpenAI(
                base_url=self.config.base_url,
                api_key=self.config.api_key,
                http_client=http_client,
            )
        return self._client

    @property
    def snapshot(self) -> SkillSnapshot:
        """Get the current skills snapshot."""
        return self.engine.get_snapshot()

    @property
    def skills(self) -> list[Skill]:
        """Get eligible skills."""
        return self.snapshot.skills

    @property
    def user_invocable_skills(self) -> list[Skill]:
        """Get skills that can be invoked by user commands."""
        return [
            s for s in self.skills
            if s.metadata.invocation.user_invocable
        ]

    def get_skill(self, name: str) -> Skill | None:
        """Get a skill by name."""
        return self.snapshot.get_skill(name)

    def build_system_prompt(self) -> str:
        """Build the complete system prompt with skills injected."""
        parts = []

        # Base system prompt
        if self.config.system_prompt:
            parts.append(self.config.system_prompt)

        # Skills prompt
        skills_prompt = self.snapshot.prompt
        if skills_prompt:
            parts.append(skills_prompt)

        # User-invocable skills hint
        invocable = self.user_invocable_skills
        if invocable:
            skill_list = ", ".join(f"/{s.name}" for s in invocable)
            parts.append(
                f"\n<user-invocable-skills>\n"
                f"The following skills are available for the user to invoke:\n"
                f"{skill_list}\n"
                f"When the user types a skill name (e.g., /pdf), provide guidance on using that skill.\n"
                f"</user-invocable-skills>"
            )

        return "\n\n".join(parts)

    def get_tools(self) -> list[dict[str, Any]]:
        """Get tool definitions for function calling."""
        if not self.config.enable_tools:
            return []

        return [
            {
                "type": "function",
                "function": {
                    "name": "execute",
                    "description": "Execute a shell command and return the output. Use this to run scripts, CLI tools, or any shell command.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "command": {
                                "type": "string",
                                "description": "The shell command to execute",
                            },
                            "cwd": {
                                "type": "string",
                                "description": "Working directory for the command (optional)",
                            },
                        },
                        "required": ["command"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "execute_script",
                    "description": "Execute a multi-line shell script. Use this for complex operations that require multiple commands.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "script": {
                                "type": "string",
                                "description": "The shell script content to execute",
                            },
                            "cwd": {
                                "type": "string",
                                "description": "Working directory for the script (optional)",
                            },
                        },
                        "required": ["script"],
                    },
                },
            },
        ]

    def _format_messages(
        self,
        messages: list[AgentMessage],
    ) -> list[dict[str, Any]]:
        """Format messages for the OpenAI API."""
        formatted = []

        # Add system prompt
        system_prompt = self.build_system_prompt()
        if system_prompt:
            formatted.append({
                "role": "system",
                "content": system_prompt,
            })

        # Add conversation messages
        for msg in messages:
            if msg.role == "tool":
                formatted.append({
                    "role": "tool",
                    "content": msg.content,
                    "tool_call_id": msg.tool_call_id,
                })
            elif msg.tool_calls:
                formatted.append({
                    "role": "assistant",
                    "content": msg.content or None,
                    "tool_calls": [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": tc["arguments"],
                            },
                        }
                        for tc in msg.tool_calls
                    ],
                })
            else:
                formatted.append({
                    "role": msg.role,
                    "content": msg.content,
                })

        return formatted

    async def _call_llm(
        self,
        messages: list[AgentMessage],
        stream: bool = False,
    ) -> AgentMessage:
        """Call the LLM and return the response."""
        formatted = self._format_messages(messages)

        # Build request
        request_kwargs: dict[str, Any] = {
            "model": self.config.model,
            "messages": formatted,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }

        # Add tools
        tools = self.get_tools()
        if tools:
            request_kwargs["tools"] = tools

        # Add reasoning split for MiniMax
        if self.config.enable_reasoning:
            request_kwargs["extra_body"] = {"reasoning_split": True}

        # Call API
        response = await self.client.chat.completions.create(**request_kwargs)

        choice = response.choices[0]
        content = choice.message.content or ""
        reasoning = None

        # Extract reasoning if available (MiniMax)
        if hasattr(choice.message, "reasoning_details"):
            reasoning = choice.message.reasoning_details

        # Extract tool calls
        tool_calls = []
        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                tool_calls.append({
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                })

        return AgentMessage(
            role="assistant",
            content=content,
            tool_calls=tool_calls,
            reasoning=reasoning,
            metadata={
                "finish_reason": choice.finish_reason,
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                    "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                },
            },
        )

    async def _execute_tool(self, tool_call: dict[str, Any]) -> str:
        """Execute a tool call and return the result."""
        name = tool_call.get("name", "")
        args_str = tool_call.get("arguments", "{}")

        try:
            args = json.loads(args_str)
        except json.JSONDecodeError:
            return f"Error: Invalid JSON arguments: {args_str}"

        logger.debug("Executing tool %s with args: %s", name, args)

        if name == "execute":
            command = args.get("command", "")
            cwd = args.get("cwd")
            result = await self.engine.execute(command, cwd=cwd)
            if result.success:
                return result.output or "(no output)"
            return f"Error (exit {result.exit_code}): {result.error}"

        if name == "execute_script":
            script = args.get("script", "")
            cwd = args.get("cwd")
            result = await self.engine.execute_script(script, cwd=cwd)
            if result.success:
                return result.output or "(no output)"
            return f"Error (exit {result.exit_code}): {result.error}"

        return f"Error: Unknown tool '{name}'"

    def _check_skill_invocation(self, user_input: str) -> Skill | None:
        """Check if user input is a skill invocation (e.g., /pdf)."""
        match = re.match(r"^/(\S+)", user_input.strip())
        if match:
            skill_name = match.group(1)
            return self.get_skill(skill_name)
        return None

    async def chat(
        self,
        user_input: str,
        reset: bool = False,
    ) -> AgentMessage:
        """
        Send a message and get a response.

        Args:
            user_input: User message
            reset: Clear conversation history before sending

        Returns:
            Assistant response
        """
        if reset:
            self._conversation = []

        # Check for skill invocation
        invoked_skill = self._check_skill_invocation(user_input)
        if invoked_skill:
            # Inject skill content into user message
            skill_context = (
                f"[User invoked skill: /{invoked_skill.name}]\n\n"
                f"<skill-content name=\"{invoked_skill.name}\">\n"
                f"{invoked_skill.content}\n"
                f"</skill-content>\n\n"
                f"User input: {user_input}"
            )
            self._conversation.append(AgentMessage(role="user", content=skill_context))
        else:
            self._conversation.append(AgentMessage(role="user", content=user_input))

        # Run agent loop
        for turn in range(self.config.max_turns):
            response = await self._call_llm(self._conversation)
            self._conversation.append(response)

            # Check if done (no tool calls)
            if not response.tool_calls:
                return response

            # Execute tools if auto_execute is enabled
            if not self.config.auto_execute:
                return response

            # Execute each tool call
            for tool_call in response.tool_calls:
                result = await self._execute_tool(tool_call)
                self._conversation.append(
                    AgentMessage(
                        role="tool",
                        content=result,
                        tool_call_id=tool_call["id"],
                        name=tool_call["name"],
                    )
                )

        # Max turns reached
        return AgentMessage(
            role="assistant",
            content="[Max turns reached. Please continue the conversation.]",
        )

    async def chat_stream(
        self,
        user_input: str,
        reset: bool = False,
    ) -> AsyncIterator[str]:
        """
        Stream a chat response.

        Args:
            user_input: User message
            reset: Clear conversation history

        Yields:
            Response text chunks
        """
        if reset:
            self._conversation = []

        self._conversation.append(AgentMessage(role="user", content=user_input))
        formatted = self._format_messages(self._conversation)

        request_kwargs: dict[str, Any] = {
            "model": self.config.model,
            "messages": formatted,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "stream": True,
        }

        stream = await self.client.chat.completions.create(**request_kwargs)

        full_content = ""
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
                full_content += content
                yield content

        self._conversation.append(AgentMessage(role="assistant", content=full_content))

    def clear_history(self) -> None:
        """Clear conversation history."""
        self._conversation = []

    def get_history(self) -> list[AgentMessage]:
        """Get conversation history."""
        return list(self._conversation)

    async def start_watching(self) -> None:
        """Start watching skill directories for changes."""
        if not self.config.watch_skills:
            return

        def on_change(changed: set[Path]) -> None:
            logger.info("Skills changed: %s", [p.name for p in changed])
            for callback in self._on_skill_change:
                callback(changed)

        await self.engine.start_watching(on_change)

    async def stop_watching(self) -> None:
        """Stop watching skill directories."""
        await self.engine.stop_watching()

    def on_skill_change(self, callback: Callable[[set[Path]], None]) -> None:
        """Register a callback for skill file changes."""
        self._on_skill_change.append(callback)

    async def run_interactive(
        self,
        prompt: str = "You: ",
        greeting: str | None = None,
    ) -> None:
        """
        Run an interactive chat loop.

        Args:
            prompt: Input prompt string
            greeting: Optional greeting message
        """
        if greeting:
            print(greeting)

        print(f"Loaded {len(self.skills)} skills: {', '.join(s.name for s in self.skills)}")
        print("Type /quit to exit, /clear to reset conversation, /skills to list skills\n")

        while True:
            try:
                user_input = input(prompt).strip()
            except (EOFError, KeyboardInterrupt):
                print("\nGoodbye!")
                break

            if not user_input:
                continue

            # Handle special commands
            if user_input.lower() in ("/quit", "/exit", "/q"):
                print("Goodbye!")
                break
            if user_input.lower() == "/clear":
                self.clear_history()
                print("Conversation cleared.\n")
                continue
            if user_input.lower() == "/skills":
                print("Available skills:")
                for skill in self.skills:
                    emoji = skill.metadata.emoji or "🔧"
                    invocable = "✓" if skill.metadata.invocation.user_invocable else " "
                    print(f"  {emoji} {skill.name} [{invocable}] - {skill.description[:50]}...")
                print()
                continue

            # Chat
            try:
                response = await self.chat(user_input)
                print(f"\nAssistant: {response.content}\n")
            except Exception as e:
                print(f"\nError: {e}\n")


# Convenience function for quick setup
async def create_agent(
    skill_dirs: list[str | Path] | None = None,
    system_prompt: str = "",
    **kwargs: Any,
) -> AgentRunner:
    """
    Create and initialize an agent runner.

    Args:
        skill_dirs: Directories to load skills from
        system_prompt: Base system prompt
        **kwargs: Additional AgentConfig parameters

    Returns:
        Initialized AgentRunner

    Example:
        agent = await create_agent(
            skill_dirs=["./skills"],
            system_prompt="You are a helpful assistant.",
        )
        response = await agent.chat("Hello!")
    """
    dirs = [Path(d) if isinstance(d, str) else d for d in (skill_dirs or [])]
    agent = AgentRunner.create(
        skill_dirs=dirs,
        system_prompt=system_prompt,
        **kwargs,
    )

    if agent.config.watch_skills:
        await agent.start_watching()

    return agent
