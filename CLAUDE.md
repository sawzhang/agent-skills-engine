# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SkillKit is a framework-agnostic skills execution engine for LLM agents. It provides a plugin-based system for defining, loading, filtering, and executing skills (capabilities) that can be made available to large language models. Aligned with the Claude Agent Skills architecture (progressive disclosure, on-demand loading, per-skill model/tools).

## Commands

```bash
# Install dependencies
uv sync

# Install with optional adapters
uv add -e ".[openai]"
uv add -e ".[anthropic]"

# Run all tests
pytest

# Run a single test file
pytest tests/test_engine.py

# Run a specific test
pytest tests/test_engine.py::test_function_name -v

# Linting and formatting
ruff check src/
ruff format src/

# Type checking
mypy src/
```

## Architecture

The engine uses a pipeline architecture with four extensible subsystems:

```
Skill Files (Markdown+YAML) → [Loader] → [Filter] → [Runtime] → [Adapter]
```

### Core Components

- **Engine** (`engine.py`): Orchestrates the entire pipeline - loads skills from directories, applies filters, generates prompts, and executes commands
- **Agent** (`agent.py`): `AgentRunner` with on-demand skill loading via `skill` tool, `$ARGUMENTS` substitution, `context: fork`, `!`cmd`` dynamic injection, per-skill model switching
- **Models** (`models.py`): Data structures including `Skill`, `SkillMetadata`, `SkillRequirements`, `SkillSnapshot`
- **Config** (`config.py`): `SkillsConfig` for directory management, filtering options, per-skill overrides

### Plugin Subsystems

Each subsystem has an abstract base class and reference implementation:

| Subsystem | Base Class | Implementation | Purpose |
|-----------|------------|----------------|---------|
| Loaders | `SkillLoader` | `MarkdownSkillLoader` | Parse skill files (Markdown + YAML frontmatter) |
| Filters | `SkillFilter` | `DefaultSkillFilter` | Check eligibility (bins, env vars, OS, config) |
| Runtimes | `SkillRuntime` | `BashRuntime`, `CodeModeRuntime` | Execute commands with timeout and env injection |
| Adapters | `LLMAdapter` | `OpenAIAdapter`, `AnthropicAdapter` | Integrate with LLM providers |

### Skill Definition Format

Skills are defined as Markdown files with YAML frontmatter, located at `skills/<name>/SKILL.md`:

```yaml
---
name: skill-name
description: What the skill does
model: claude-sonnet-4-5-20250514    # Per-skill model override
context: fork                  # Isolated subagent execution
allowed-tools: [Read, Grep]   # Tool restrictions
argument-hint: "<query>"       # Autocomplete hint
hooks:
  PreToolExecution: "echo pre"
metadata:
  emoji: "🔧"
  primary_env: "API_KEY"
  requires:
    bins: ["git"]           # ALL must exist
    any_bins: ["npm", "pnpm"] # At least ONE must exist
    env: ["GITHUB_TOKEN"]
    os: ["darwin", "linux"]
---
# Skill content (prompt text)
Use $ARGUMENTS for dynamic input.
Current date: !`date +%Y-%m-%d`
```

### On-Demand Skill Loading

The system prompt only contains skill **names and descriptions** (metadata). Full skill content is loaded on-demand when the LLM calls the `skill` tool. This follows the progressive disclosure pattern from Claude Agent Skills.

- `AgentConfig.skill_description_budget` (default 16000) limits total chars for skill metadata in the system prompt
- The `skill` tool accepts `name` and optional `arguments` parameters
- `$ARGUMENTS`, `$1`..`$N`, `${CLAUDE_SESSION_ID}` are substituted in skill content
- `!`command`` placeholders are replaced with command stdout before sending to LLM
- Skills with `context: fork` run in an isolated child `AgentRunner`
- Skills with `model:` trigger per-skill model switching (restored after)
- Skills with `allowed-tools:` restrict which tools the LLM can use

### Skill Validation

`AgentRunner.validate_skill(skill)` enforces:
- Name: ≤64 chars, lowercase alphanumeric + hyphens, no leading hyphen
- Description: non-empty, ≤1024 chars

### CodeModeRuntime (search + execute pattern)

Inspired by Cloudflare's code-mode-mcp. Instead of exposing N tools (one per API endpoint), `CodeModeRuntime` exposes just 2 tools — `search` and `execute` — and lets the LLM write Python code against injected data and clients. Token cost is O(1) regardless of API surface area.

```python
runtime = CodeModeRuntime(
    spec=openapi_spec,              # Any data for discovery (dict, list, etc.)
    ctx={"client": httpx.Client()}, # Objects injected into execute mode
)

# search: spec only, no ctx (read-only discovery)
await runtime.search("[p for p in spec['paths'] if '/users' in p]")

# run/execute: spec + ctx (call APIs, mutate state)
await runtime.run("result = ctx['client'].get('/users')")

# Generate 2-tool definitions for LLM adapters (OpenAI format)
tools = runtime.get_tool_definitions()  # → [search, execute]
```

- **Two execution modes**: `search(code)` injects `spec` only; `run(code)` / `execute(code)` injects both `spec` and `ctx`
- **Two sandbox modes**: `"inprocess"` (exec with restricted builtins, works with any Python objects) and `"subprocess"` (child process isolation, JSON-serializable data only)
- **Safe builtins**: restricted `__import__` only allows configured modules (default: json, re, math, datetime, collections, itertools, functools, urllib.parse)
- **`get_tool_definitions()`**: generates OpenAI function-calling format tool definitions with spec hints and ctx key names
- **Drop-in replacement**: implements `SkillRuntime`, can be passed to `SkillsEngine(runtime=CodeModeRuntime(...))`
- **Result convention**: user code assigns to `result` for structured output, or uses `print()` for text output

### Key Patterns

- **Progressive Disclosure**: Only skill metadata in system prompt; full content loaded on-demand via `skill` tool
- **Environment Management**: The engine uses a context manager pattern (`env_context`) to safely backup/restore environment variables when injecting per-skill overrides
- **Snapshot Caching**: `SkillSnapshot` provides immutable point-in-time views with version tracking and content hashing for cache invalidation
- **Filter Short-circuiting**: Eligibility checks run in sequence and short-circuit on first failure, returning the reason for ineligibility
- **Per-Skill Model Switching**: `switch_model()` before skill content, restore in `finally` block
- **Fork Isolation**: `_execute_skill_forked()` creates a child `AgentRunner` with skill content as system prompt, inherits parent config
