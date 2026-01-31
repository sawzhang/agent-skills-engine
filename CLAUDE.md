# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Agent Skills Engine is a framework-agnostic skills execution engine for LLM agents. It provides a plugin-based system for defining, loading, filtering, and executing skills (capabilities) that can be made available to large language models.

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
- **Models** (`models.py`): Data structures including `Skill`, `SkillMetadata`, `SkillRequirements`, `SkillSnapshot`
- **Config** (`config.py`): `SkillsConfig` for directory management, filtering options, per-skill overrides

### Plugin Subsystems

Each subsystem has an abstract base class and reference implementation:

| Subsystem | Base Class | Implementation | Purpose |
|-----------|------------|----------------|---------|
| Loaders | `SkillLoader` | `MarkdownSkillLoader` | Parse skill files (Markdown + YAML frontmatter) |
| Filters | `SkillFilter` | `DefaultSkillFilter` | Check eligibility (bins, env vars, OS, config) |
| Runtimes | `SkillRuntime` | `BashRuntime` | Execute commands with timeout and env injection |
| Adapters | `LLMAdapter` | `OpenAIAdapter`, `AnthropicAdapter` | Integrate with LLM providers |

### Skill Definition Format

Skills are defined as Markdown files with YAML frontmatter, located at `skills/<name>/SKILL.md`:

```yaml
---
name: skill-name
description: What the skill does
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
```

### Key Patterns

- **Environment Management**: The engine uses a context manager pattern (`env_context`) to safely backup/restore environment variables when injecting per-skill overrides
- **Snapshot Caching**: `SkillSnapshot` provides immutable point-in-time views with version tracking and content hashing for cache invalidation
- **Filter Short-circuiting**: Eligibility checks run in sequence and short-circuit on first failure, returning the reason for ineligibility
