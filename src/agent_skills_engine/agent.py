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
from agent_skills_engine.context import ContextManager, estimate_messages_tokens
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

# Auto-load .env file from current directory or parent directories
load_dotenv()
from agent_skills_engine.adapters.registry import AdapterRegistry
from agent_skills_engine.engine import SkillsEngine
from agent_skills_engine.logging import get_logger
from agent_skills_engine.model_registry import (
    ModelDefinition,
    ModelRegistry,
    ThinkingLevel,
    TokenUsage,
    Transport,
)
from agent_skills_engine.models import Skill, SkillSnapshot

logger = get_logger("agent")


class AgentAbortedError(Exception):
    """Raised when the agent operation is aborted via ``abort()``."""

    pass


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
    token_usage: TokenUsage | None = None  # Token usage for this response


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

    # Thinking budget
    thinking_level: ThinkingLevel | None = None  # None = off, backward compatible

    # Transport
    transport: Transport = "sse"  # Default SSE, backward compatible

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
        events: EventBus | None = None,
        model_registry: ModelRegistry | None = None,
        context_manager: ContextManager | None = None,
        adapter_registry: AdapterRegistry | None = None,
    ) -> None:
        self.engine = engine
        self.config = config or AgentConfig.from_env()
        self.events = events or EventBus()
        self.model_registry = model_registry
        self.context_manager = context_manager
        self.adapter_registry = adapter_registry or AdapterRegistry()
        self._active_adapter_name: str | None = None
        self._client: Any = None
        self._conversation: list[AgentMessage] = []
        self._cumulative_usage = TokenUsage()
        self._on_skill_change: list[Callable[[set[Path]], None]] = []

        # Abort / steering / follow-up
        self._abort_event = asyncio.Event()
        self._steering_queue: asyncio.Queue[str] = asyncio.Queue()
        self._followup_queue: asyncio.Queue[str] = asyncio.Queue()

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
    def model_definition(self) -> ModelDefinition | None:
        """Get the ModelDefinition for the current model, if available."""
        if self.model_registry is None:
            return None
        return self.model_registry.get(self.config.model)

    @property
    def cumulative_usage(self) -> TokenUsage:
        """Get cumulative token usage across all calls in this session."""
        return self._cumulative_usage

    def reset_usage(self) -> None:
        """Reset cumulative token usage to zero."""
        self._cumulative_usage = TokenUsage()

    # ------------------------------------------------------------------
    # Adapter registry
    # ------------------------------------------------------------------

    @property
    def active_adapter(self) -> Any:
        """
        Get the currently active LLM adapter, if one is set.

        Returns the adapter selected via ``set_adapter()`` or the registry
        default. Returns ``None`` if no adapter is registered (in which case
        the built-in OpenAI client path is used).
        """
        from agent_skills_engine.adapters.base import LLMAdapter

        if self._active_adapter_name is not None:
            try:
                return self.adapter_registry.get(
                    self._active_adapter_name, engine=self.engine,
                )
            except KeyError:
                logger.warning(
                    "Active adapter '%s' not found, falling back",
                    self._active_adapter_name,
                )
                self._active_adapter_name = None

        return self.adapter_registry.get_default(engine=self.engine)

    def set_adapter(self, name: str) -> None:
        """
        Switch the active LLM adapter by name.

        The adapter must already be registered in the ``adapter_registry``.

        Args:
            name: Adapter name

        Raises:
            KeyError: If adapter not registered
        """
        if not self.adapter_registry.has(name):
            available = ", ".join(self.adapter_registry.list_adapters()) or "(none)"
            raise KeyError(
                f"Adapter '{name}' not found. Available: {available}"
            )
        self._active_adapter_name = name
        logger.info("Switched active adapter to: %s", name)

    # ------------------------------------------------------------------
    # Abort / Steering / Follow-up
    # ------------------------------------------------------------------

    @property
    def is_aborted(self) -> bool:
        """Check if the current operation has been aborted."""
        return self._abort_event.is_set()

    def abort(self) -> None:
        """
        Abort the current agent operation immediately.

        Sets the abort signal that is checked between tool executions,
        during LLM streaming, and passed to runtime execution. The
        agent loop will exit with finish_reason="aborted".

        Call ``reset_abort()`` before starting a new chat after aborting.
        """
        self._abort_event.set()

    def reset_abort(self) -> None:
        """Clear the abort signal so the agent can be used again."""
        self._abort_event.clear()

    def steer(self, message: str) -> None:
        """
        Inject a steering message into the current agent loop.

        The agent will stop executing remaining tool calls for the current
        turn and start a new turn with this message appended to the
        conversation as a user message. This allows correcting the agent
        mid-execution without waiting for the full loop to complete.

        Args:
            message: Steering instruction to inject.
        """
        self._steering_queue.put_nowait(message)

    def follow_up(self, message: str) -> None:
        """
        Queue a follow-up message to send after the current loop finishes.

        Unlike ``steer()`` which interrupts the current tool chain,
        ``follow_up()`` waits for the current loop to complete naturally,
        then starts a new agent loop with this message.

        Args:
            message: Follow-up message to process next.
        """
        self._followup_queue.put_nowait(message)

    def _check_abort(self) -> None:
        """Raise AgentAbortedError if the abort signal is set."""
        if self._abort_event.is_set():
            raise AgentAbortedError("Agent operation aborted")

    def _drain_steering(self) -> str | None:
        """Non-blocking check for a steering message."""
        try:
            return self._steering_queue.get_nowait()
        except asyncio.QueueEmpty:
            return None

    def _drain_followup(self) -> str | None:
        """Non-blocking check for a follow-up message."""
        try:
            return self._followup_queue.get_nowait()
        except asyncio.QueueEmpty:
            return None

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

    def _convert_to_adapter_messages(
        self,
        messages: list[AgentMessage],
    ) -> list[Any]:
        """Convert AgentMessages to adapter Message format."""
        from agent_skills_engine.adapters.base import Message

        result: list[Message] = []
        for msg in messages:
            metadata: dict[str, Any] = dict(msg.metadata) if msg.metadata else {}
            if msg.tool_call_id:
                metadata["tool_call_id"] = msg.tool_call_id
            if msg.tool_calls:
                metadata["tool_calls"] = msg.tool_calls
            if msg.name:
                metadata["name"] = msg.name
            result.append(Message(role=msg.role, content=msg.content, metadata=metadata))
        return result

    def _adapter_response_to_agent_message(
        self,
        response: Any,
    ) -> AgentMessage:
        """Convert an adapter AgentResponse to an AgentMessage."""
        token_usage = response.token_usage or TokenUsage()
        self._cumulative_usage += token_usage

        return AgentMessage(
            role="assistant",
            content=response.content,
            tool_calls=response.tool_calls or [],
            token_usage=token_usage,
            metadata={
                "finish_reason": response.finish_reason or "",
                "usage": response.usage or {},
            },
        )

    async def _call_llm(
        self,
        messages: list[AgentMessage],
        stream: bool = False,
    ) -> AgentMessage:
        """Call the LLM and return the response.

        If an adapter is active (via ``adapter_registry``), delegates to
        the adapter's ``chat()`` method. Otherwise uses the built-in
        OpenAI client directly.
        """
        adapter = self.active_adapter
        if adapter is not None:
            adapter_msgs = self._convert_to_adapter_messages(messages)
            system_prompt = self.build_system_prompt()
            response = await adapter.chat(
                adapter_msgs,
                system_prompt=system_prompt,
                thinking_level=self.config.thinking_level,
            )
            return self._adapter_response_to_agent_message(response)

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

        # Extract token usage
        token_usage = TokenUsage(
            input_tokens=response.usage.prompt_tokens if response.usage else 0,
            output_tokens=response.usage.completion_tokens if response.usage else 0,
        )
        self._cumulative_usage += token_usage

        return AgentMessage(
            role="assistant",
            content=content,
            tool_calls=tool_calls,
            reasoning=reasoning,
            token_usage=token_usage,
            metadata={
                "finish_reason": choice.finish_reason,
                "usage": {
                    "prompt_tokens": token_usage.input_tokens,
                    "completion_tokens": token_usage.output_tokens,
                },
            },
        )

    async def _execute_tool(
        self,
        tool_call: dict[str, Any],
        on_output: Callable[[str], None] | None = None,
    ) -> str:
        """Execute a tool call and return the result.

        Args:
            tool_call: Tool call dict with name, arguments, id.
            on_output: Optional callback for streaming intermediate output.
                       Invoked with each line as it arrives from the process.
        """
        name = tool_call.get("name", "")
        args_str = tool_call.get("arguments", "{}")

        try:
            args = json.loads(args_str)
        except json.JSONDecodeError:
            return f"Error: Invalid JSON arguments: {args_str}"

        logger.debug("Executing tool %s with args: %s", name, args)

        # Pass abort signal to runtime so it can kill long-running processes
        abort = self._abort_event if self._abort_event.is_set() is False else None
        # Always pass it — runtime checks .is_set()
        abort = self._abort_event

        if name == "execute":
            command = args.get("command", "")
            cwd = args.get("cwd")
            result = await self.engine.execute(
                command, cwd=cwd, on_output=on_output, abort_signal=abort,
            )
            if result.success:
                return result.output or "(no output)"
            return f"Error (exit {result.exit_code}): {result.error}"

        if name == "execute_script":
            script = args.get("script", "")
            cwd = args.get("cwd")
            result = await self.engine.execute_script(
                script, cwd=cwd, on_output=on_output, abort_signal=abort,
            )
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

        Events emitted during the lifecycle:
        - ``input``: When user input is received (can transform or handle it)
        - ``agent_start``: Before the first LLM call
        - ``turn_start``: Before each LLM round-trip
        - ``context_transform``: Before messages are sent to LLM (can prune/inject)
        - ``turn_end``: After each LLM round-trip
        - ``before_tool_call``: Before each tool execution (can block or modify)
        - ``after_tool_result``: After each tool returns (can modify result)
        - ``agent_end``: After the agent loop finishes

        Args:
            user_input: User message
            reset: Clear conversation history before sending

        Returns:
            Assistant response
        """
        if reset:
            self._conversation = []

        # --- input event ---
        input_results = await self.events.emit(INPUT, InputEvent(user_input=user_input))
        for r in input_results:
            if isinstance(r, InputEventResult):
                if r.action == "handled" and r.response is not None:
                    return AgentMessage(role="assistant", content=r.response)
                if r.action == "transform" and r.transformed_input is not None:
                    user_input = r.transformed_input

        # Check for skill invocation
        invoked_skill = self._check_skill_invocation(user_input)
        if invoked_skill:
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

        # --- agent_start event ---
        await self.events.emit(
            AGENT_START,
            AgentStartEvent(
                user_input=user_input,
                system_prompt=self.build_system_prompt(),
                model=self.config.model,
            ),
        )

        finish_reason = "complete"
        error_msg: str | None = None
        final_response: AgentMessage | None = None

        try:
            for turn in range(self.config.max_turns):
                # --- abort check ---
                self._check_abort()

                # --- steering check ---
                steering = self._drain_steering()
                if steering:
                    self._conversation.append(
                        AgentMessage(role="user", content=steering)
                    )

                # --- turn_start event ---
                await self.events.emit(
                    TURN_START,
                    TurnStartEvent(turn=turn, message_count=len(self._conversation)),
                )

                # --- context_transform event ---
                messages_for_llm = list(self._conversation)
                if self.events.has_handlers(CONTEXT_TRANSFORM):
                    ctx_results = await self.events.emit(
                        CONTEXT_TRANSFORM,
                        ContextTransformEvent(messages=messages_for_llm, turn=turn),
                    )
                    for r in ctx_results:
                        if isinstance(r, ContextTransformEventResult) and r.messages is not None:
                            messages_for_llm = r.messages

                # --- context compaction ---
                if self.context_manager and self.context_manager.should_compact(messages_for_llm):
                    messages_for_llm = await self.context_manager.compact(messages_for_llm)

                response = await self._call_llm(messages_for_llm)
                self._conversation.append(response)

                # --- turn_end event ---
                await self.events.emit(
                    TURN_END,
                    TurnEndEvent(
                        turn=turn,
                        has_tool_calls=bool(response.tool_calls),
                        content=response.content,
                        tool_call_count=len(response.tool_calls),
                    ),
                )

                # Check if done (no tool calls)
                if not response.tool_calls:
                    final_response = response
                    return response

                # Execute tools if auto_execute is enabled
                if not self.config.auto_execute:
                    final_response = response
                    return response

                # Execute each tool call
                steered = False
                for tool_call in response.tool_calls:
                    # --- abort check between tools ---
                    self._check_abort()

                    # --- steering check between tools ---
                    steering = self._drain_steering()
                    if steering:
                        self._conversation.append(
                            AgentMessage(role="user", content=steering)
                        )
                        steered = True
                        break  # Stop executing remaining tools, start new turn

                    tc_id = tool_call["id"]
                    tc_name = tool_call["name"]
                    tc_args_str = tool_call.get("arguments", "{}")
                    try:
                        tc_args = json.loads(tc_args_str)
                    except json.JSONDecodeError:
                        tc_args = {}

                    # --- before_tool_call event ---
                    btc_results = await self.events.emit(
                        BEFORE_TOOL_CALL,
                        BeforeToolCallEvent(
                            tool_call_id=tc_id,
                            tool_name=tc_name,
                            args=tc_args,
                            turn=turn,
                        ),
                    )

                    blocked = False
                    for r in btc_results:
                        if isinstance(r, ToolCallEventResult):
                            if r.block:
                                blocked = True
                                block_reason = r.reason or "Blocked by event handler"
                                self._conversation.append(
                                    AgentMessage(
                                        role="tool",
                                        content=f"[Blocked] {block_reason}",
                                        tool_call_id=tc_id,
                                        name=tc_name,
                                    )
                                )
                                break
                            if r.modified_args is not None:
                                tc_args = r.modified_args
                                # Re-serialize for _execute_tool
                                tool_call = {
                                    **tool_call,
                                    "arguments": json.dumps(tc_args),
                                }

                    if blocked:
                        continue

                    # Build on_output callback for tool_execution_update events
                    _tc_id, _tc_name, _turn = tc_id, tc_name, turn

                    def _on_output(line: str, _tid=_tc_id, _tname=_tc_name, _t=_turn) -> None:
                        if self.events.has_handlers(TOOL_EXECUTION_UPDATE):
                            # Fire-and-forget in sync context — schedule on event loop
                            try:
                                loop = asyncio.get_running_loop()
                                loop.create_task(
                                    self.events.emit(
                                        TOOL_EXECUTION_UPDATE,
                                        ToolExecutionUpdateEvent(
                                            tool_call_id=_tid,
                                            tool_name=_tname,
                                            output=line,
                                            turn=_t,
                                        ),
                                    )
                                )
                            except RuntimeError:
                                pass

                    result = await self._execute_tool(tool_call, on_output=_on_output)

                    # --- after_tool_result event ---
                    atr_results = await self.events.emit(
                        AFTER_TOOL_RESULT,
                        AfterToolResultEvent(
                            tool_call_id=tc_id,
                            tool_name=tc_name,
                            args=tc_args,
                            result=result,
                            turn=turn,
                        ),
                    )
                    for r in atr_results:
                        if isinstance(r, ToolResultEventResult) and r.modified_result is not None:
                            result = r.modified_result

                    self._conversation.append(
                        AgentMessage(
                            role="tool",
                            content=result,
                            tool_call_id=tc_id,
                            name=tc_name,
                        )
                    )

                if steered:
                    continue  # Start a new turn with the steering message

            # Max turns reached
            finish_reason = "max_turns"
            final_response = AgentMessage(
                role="assistant",
                content="[Max turns reached. Please continue the conversation.]",
            )
            return final_response

        except AgentAbortedError:
            finish_reason = "aborted"
            final_response = AgentMessage(
                role="assistant",
                content="[Aborted]",
            )
            return final_response

        except Exception as e:
            finish_reason = "error"
            error_msg = str(e)
            raise

        finally:
            # --- agent_end event ---
            await self.events.emit(
                AGENT_END,
                AgentEndEvent(
                    user_input=user_input,
                    total_turns=len([
                        m for m in self._conversation
                        if m.role == "assistant" and m not in (self._conversation[:1])
                    ]),
                    finish_reason=finish_reason,
                    error=error_msg,
                ),
            )

    async def _call_llm_stream(
        self,
        messages: list[AgentMessage],
    ) -> AsyncIterator[StreamEvent]:
        """
        Call the LLM with streaming and yield StreamEvents.

        If an adapter is active, delegates to the adapter's
        ``chat_stream_events()``. Otherwise maps OpenAI streaming chunks
        to structured events (including MiniMax reasoning).

        The caller is responsible for collecting the final AgentMessage from
        the yielded events.
        """
        adapter = self.active_adapter
        if adapter is not None:
            adapter_msgs = self._convert_to_adapter_messages(messages)
            system_prompt = self.build_system_prompt()
            async for event in adapter.chat_stream_events(
                adapter_msgs,
                system_prompt=system_prompt,
                thinking_level=self.config.thinking_level,
            ):
                yield event
            return

        formatted = self._format_messages(messages)

        request_kwargs: dict[str, Any] = {
            "model": self.config.model,
            "messages": formatted,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "stream": True,
        }

        tools = self.get_tools()
        if tools:
            request_kwargs["tools"] = tools

        if self.config.enable_reasoning:
            request_kwargs["extra_body"] = {"reasoning_split": True}

        stream = await self.client.chat.completions.create(**request_kwargs)

        text_started = False
        reasoning_started = False
        # Track active tool calls: index -> {id, name, args}
        active_tool_calls: dict[int, dict[str, str]] = {}

        async for chunk in stream:
            if not chunk.choices:
                continue

            delta = chunk.choices[0].delta

            # --- Reasoning content (MiniMax) ---
            reasoning_content = getattr(delta, "reasoning_content", None)
            if reasoning_content:
                if not reasoning_started:
                    yield StreamEvent(type="thinking_start")
                    reasoning_started = True
                yield StreamEvent(type="thinking_delta", content=reasoning_content)

            # --- Text content ---
            if delta.content:
                if reasoning_started:
                    yield StreamEvent(type="thinking_end")
                    reasoning_started = False
                if not text_started:
                    yield StreamEvent(type="text_start")
                    text_started = True
                yield StreamEvent(type="text_delta", content=delta.content)

            # --- Tool calls ---
            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in active_tool_calls:
                        tc_id = tc_delta.id or ""
                        tc_name = (
                            tc_delta.function.name
                            if tc_delta.function and tc_delta.function.name
                            else ""
                        )
                        active_tool_calls[idx] = {"id": tc_id, "name": tc_name, "args": ""}

                        if text_started:
                            yield StreamEvent(type="text_end")
                            text_started = False
                        if reasoning_started:
                            yield StreamEvent(type="thinking_end")
                            reasoning_started = False

                        yield StreamEvent(
                            type="tool_call_start",
                            tool_call_id=tc_id,
                            tool_name=tc_name,
                        )

                    if tc_delta.function and tc_delta.function.arguments:
                        active_tool_calls[idx]["args"] += tc_delta.function.arguments
                        yield StreamEvent(
                            type="tool_call_delta",
                            tool_call_id=active_tool_calls[idx]["id"],
                            tool_name=active_tool_calls[idx]["name"],
                            args_delta=tc_delta.function.arguments,
                        )

            # --- Finish ---
            finish_reason = chunk.choices[0].finish_reason
            if finish_reason is not None:
                if reasoning_started:
                    yield StreamEvent(type="thinking_end")
                if text_started:
                    yield StreamEvent(type="text_end")

                for _idx, tc_info in active_tool_calls.items():
                    yield StreamEvent(
                        type="tool_call_end",
                        tool_call_id=tc_info["id"],
                        tool_name=tc_info["name"],
                    )

                yield StreamEvent(type="done", finish_reason=finish_reason)

    async def chat_stream_events(
        self,
        user_input: str,
        reset: bool = False,
    ) -> AsyncIterator[StreamEvent]:
        """
        Stream structured events for the full agent loop.

        This is the richest streaming interface. It yields fine-grained events
        for every phase of the agent lifecycle: text streaming, thinking,
        tool calls, tool results, turn boundaries, and completion.

        Events emitted:
        - ``turn_start`` / ``turn_end`` — Turn lifecycle
        - ``thinking_start`` / ``thinking_delta`` / ``thinking_end`` — Reasoning
        - ``text_start`` / ``text_delta`` / ``text_end`` — Response text
        - ``tool_call_start`` / ``tool_call_delta`` / ``tool_call_end`` — Tool invocations
        - ``tool_result`` — Tool execution output
        - ``done`` / ``error`` — Completion

        Args:
            user_input: User message
            reset: Clear conversation history before sending

        Yields:
            StreamEvent objects
        """
        if reset:
            self._conversation = []

        # --- input event ---
        input_results = await self.events.emit(INPUT, InputEvent(user_input=user_input))
        for r in input_results:
            if isinstance(r, InputEventResult):
                if r.action == "handled" and r.response is not None:
                    yield StreamEvent(type="text_start")
                    yield StreamEvent(type="text_delta", content=r.response)
                    yield StreamEvent(type="text_end")
                    yield StreamEvent(type="done", finish_reason="complete")
                    return
                if r.action == "transform" and r.transformed_input is not None:
                    user_input = r.transformed_input

        # Check for skill invocation
        invoked_skill = self._check_skill_invocation(user_input)
        if invoked_skill:
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

        # --- agent_start event ---
        await self.events.emit(
            AGENT_START,
            AgentStartEvent(
                user_input=user_input,
                system_prompt=self.build_system_prompt(),
                model=self.config.model,
            ),
        )

        finish_reason = "complete"
        error_msg: str | None = None

        try:
            for turn in range(self.config.max_turns):
                # --- abort check ---
                self._check_abort()

                # --- steering check ---
                steering = self._drain_steering()
                if steering:
                    self._conversation.append(
                        AgentMessage(role="user", content=steering)
                    )

                yield StreamEvent(type="turn_start", turn=turn)

                # --- context_transform event ---
                messages_for_llm = list(self._conversation)
                if self.events.has_handlers(CONTEXT_TRANSFORM):
                    ctx_results = await self.events.emit(
                        CONTEXT_TRANSFORM,
                        ContextTransformEvent(messages=messages_for_llm, turn=turn),
                    )
                    for r in ctx_results:
                        if isinstance(r, ContextTransformEventResult) and r.messages is not None:
                            messages_for_llm = r.messages

                # --- context compaction ---
                if self.context_manager and self.context_manager.should_compact(messages_for_llm):
                    messages_for_llm = await self.context_manager.compact(messages_for_llm)

                # Stream LLM response and collect the final message
                full_content = ""
                reasoning_content = ""
                tool_calls: list[dict[str, Any]] = []
                # {index: {id, name, args}}
                tc_collector: dict[int, dict[str, str]] = {}

                async for event in self._call_llm_stream(messages_for_llm):
                    # Pass through to caller
                    event.turn = turn
                    yield event

                    # Collect for building AgentMessage
                    if event.type == "text_delta":
                        full_content += event.content
                    elif event.type == "thinking_delta":
                        reasoning_content += event.content
                    elif event.type == "tool_call_start":
                        idx = len(tc_collector)
                        tc_collector[idx] = {
                            "id": event.tool_call_id or "",
                            "name": event.tool_name or "",
                            "args": "",
                        }
                    elif event.type == "tool_call_delta":
                        # Find matching collector entry
                        for _idx, tc in tc_collector.items():
                            if tc["id"] == event.tool_call_id:
                                tc["args"] += event.args_delta or ""
                                break
                    elif event.type == "tool_call_end":
                        for _idx, tc in tc_collector.items():
                            if tc["id"] == event.tool_call_id:
                                tool_calls.append({
                                    "id": tc["id"],
                                    "name": tc["name"],
                                    "arguments": tc["args"],
                                })
                                break

                # Build and store AgentMessage
                response = AgentMessage(
                    role="assistant",
                    content=full_content,
                    tool_calls=tool_calls,
                    reasoning=reasoning_content or None,
                )
                self._conversation.append(response)

                yield StreamEvent(
                    type="turn_end",
                    turn=turn,
                    content=full_content,
                )

                # --- turn events for EventBus ---
                await self.events.emit(
                    TURN_END,
                    TurnEndEvent(
                        turn=turn,
                        has_tool_calls=bool(tool_calls),
                        content=full_content,
                        tool_call_count=len(tool_calls),
                    ),
                )

                # Done — no tool calls
                if not tool_calls:
                    finish_reason = "complete"
                    yield StreamEvent(type="done", finish_reason="complete")
                    return

                if not self.config.auto_execute:
                    finish_reason = "complete"
                    yield StreamEvent(type="done", finish_reason="complete")
                    return

                # Execute tool calls
                steered = False
                for tool_call in tool_calls:
                    # --- abort check between tools ---
                    self._check_abort()

                    # --- steering check between tools ---
                    steering = self._drain_steering()
                    if steering:
                        self._conversation.append(
                            AgentMessage(role="user", content=steering)
                        )
                        steered = True
                        break

                    tc_id = tool_call["id"]
                    tc_name = tool_call["name"]
                    tc_args_str = tool_call.get("arguments", "{}")
                    try:
                        tc_args = json.loads(tc_args_str)
                    except json.JSONDecodeError:
                        tc_args = {}

                    # --- before_tool_call event ---
                    btc_results = await self.events.emit(
                        BEFORE_TOOL_CALL,
                        BeforeToolCallEvent(
                            tool_call_id=tc_id, tool_name=tc_name,
                            args=tc_args, turn=turn,
                        ),
                    )

                    blocked = False
                    for r in btc_results:
                        if isinstance(r, ToolCallEventResult):
                            if r.block:
                                blocked = True
                                block_reason = r.reason or "Blocked by event handler"
                                self._conversation.append(AgentMessage(
                                    role="tool",
                                    content=f"[Blocked] {block_reason}",
                                    tool_call_id=tc_id, name=tc_name,
                                ))
                                yield StreamEvent(
                                    type="tool_result",
                                    tool_call_id=tc_id, tool_name=tc_name,
                                    content=f"[Blocked] {block_reason}",
                                    turn=turn,
                                )
                                break
                            if r.modified_args is not None:
                                tc_args = r.modified_args
                                tool_call = {
                                    **tool_call,
                                    "arguments": json.dumps(tc_args),
                                }

                    if blocked:
                        continue

                    # Build on_output callback for tool_output stream events
                    _tc_id, _tc_name, _turn = tc_id, tc_name, turn
                    _output_events: list[StreamEvent] = []

                    def _on_output(line: str, _tid=_tc_id, _tname=_tc_name, _t=_turn) -> None:
                        _output_events.append(
                            StreamEvent(
                                type="tool_output",
                                tool_call_id=_tid,
                                tool_name=_tname,
                                content=line,
                                turn=_t,
                            )
                        )

                    result = await self._execute_tool(tool_call, on_output=_on_output)

                    # Yield any tool_output events collected during execution
                    for oe in _output_events:
                        yield oe

                    # --- after_tool_result event ---
                    atr_results = await self.events.emit(
                        AFTER_TOOL_RESULT,
                        AfterToolResultEvent(
                            tool_call_id=tc_id, tool_name=tc_name,
                            args=tc_args, result=result, turn=turn,
                        ),
                    )
                    for r in atr_results:
                        if isinstance(r, ToolResultEventResult) and r.modified_result is not None:
                            result = r.modified_result

                    self._conversation.append(AgentMessage(
                        role="tool", content=result,
                        tool_call_id=tc_id, name=tc_name,
                    ))

                    yield StreamEvent(
                        type="tool_result",
                        tool_call_id=tc_id, tool_name=tc_name,
                        content=result, turn=turn,
                    )

                if steered:
                    continue  # Start new turn with steering message

            # Max turns reached
            finish_reason = "max_turns"
            yield StreamEvent(type="done", finish_reason="max_turns")

        except AgentAbortedError:
            finish_reason = "aborted"
            yield StreamEvent(type="done", finish_reason="aborted")

        except Exception as e:
            finish_reason = "error"
            error_msg = str(e)
            yield StreamEvent(type="error", error=str(e))
            raise

        finally:
            await self.events.emit(
                AGENT_END,
                AgentEndEvent(
                    user_input=user_input,
                    total_turns=len([
                        m for m in self._conversation
                        if m.role == "assistant" and m not in (self._conversation[:1])
                    ]),
                    finish_reason=finish_reason,
                    error=error_msg,
                ),
            )

    async def chat_stream(
        self,
        user_input: str,
        reset: bool = False,
    ) -> AsyncIterator[str]:
        """
        Stream a chat response (text deltas only).

        This is a convenience wrapper over ``chat_stream_events()`` that
        yields only text content strings. For full event details, use
        ``chat_stream_events()`` instead.

        Args:
            user_input: User message
            reset: Clear conversation history

        Yields:
            Response text chunks
        """
        async for event in self.chat_stream_events(user_input, reset=reset):
            if event.type == "text_delta":
                yield event.content

    def clear_history(self) -> None:
        """Clear conversation history."""
        self._conversation = []

    def get_history(self) -> list[AgentMessage]:
        """Get conversation history."""
        return list(self._conversation)

    def get_context_usage(self) -> dict[str, Any]:
        """
        Get current context window usage information.

        Returns a dict with:
        - estimated_tokens: Estimated tokens in current conversation
        - context_window: Model's context window (if known)
        - usage_fraction: Fraction of context window used (0.0 - 1.0+)
        - needs_compaction: Whether compaction is recommended
        """
        estimated = estimate_messages_tokens(self._conversation)
        context_window: int | None = None
        model_def = self.model_definition
        if model_def:
            context_window = model_def.context_window
        elif self.context_manager:
            context_window = self.context_manager.context_window

        fraction = estimated / context_window if context_window else None

        return {
            "estimated_tokens": estimated,
            "context_window": context_window,
            "usage_fraction": fraction,
            "needs_compaction": (
                self.context_manager.should_compact(self._conversation)
                if self.context_manager
                else False
            ),
        }

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
        from agent_skills_engine.commands import CommandRegistry
        from agent_skills_engine.prompts import PromptTemplateLoader

        if greeting:
            print(greeting)

        # Initialize extensions
        ext_manager = self.engine.init_extensions()

        # Initialize command registry
        commands = CommandRegistry(self.engine)
        commands.sync_from_extensions(ext_manager)
        commands.sync_from_skills(self.skills)

        # Load prompt templates
        prompt_loader = PromptTemplateLoader()
        templates = prompt_loader.load_all()
        commands.sync_from_prompts(templates, prompt_loader)

        # Optional readline tab-completion
        try:
            import readline

            def completer(text: str, state: int) -> str | None:
                matches = commands.get_completions(text)
                if state < len(matches):
                    return matches[state]
                return None

            readline.set_completer(completer)
            readline.parse_and_bind("tab: complete")
        except ImportError:
            pass

        total_cmds = len(commands.list_commands())
        print(f"Loaded {len(self.skills)} skills: {', '.join(s.name for s in self.skills)}")
        print(f"Commands: /help, /skills, /reload, ... ({total_cmds} total)")
        print("Type /help for all commands, /quit to exit\n")

        while True:
            try:
                user_input = input(prompt).strip()
            except (EOFError, KeyboardInterrupt):
                print("\nGoodbye!")
                break

            if not user_input:
                continue

            # Dispatch slash commands
            if user_input.startswith("/"):
                parts = user_input.split(None, 1)
                cmd_name = parts[0].lower()
                cmd_args = parts[1] if len(parts) > 1 else ""

                result = await commands.dispatch(cmd_name, cmd_args)

                if commands.should_quit:
                    print(result.output)
                    break

                if result.handled:
                    if cmd_name == "/clear":
                        self.clear_history()
                    if result.output:
                        print(f"{result.output}\n")
                    continue

                # Not handled - pass content through to LLM
                # This covers: skill commands, prompt templates,
                # AND unknown commands (let LLM reason about them)
                passthrough = result.content or user_input
                try:
                    response = await self.chat(passthrough)
                    print(f"\nAssistant: {response.content}\n")
                except Exception as e:
                    print(f"\nError: {e}\n")
                continue

            # Regular chat
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
