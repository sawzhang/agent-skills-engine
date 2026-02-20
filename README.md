# SkillKit

A standalone, framework-agnostic skills execution engine for LLM agents. Provides a Claude Code-like experience with automatic skill discovery, loading, and execution.

## Features

- **Claude Code-like Experience**: `AgentRunner` provides auto-loading, slash commands, and tool execution
- **On-Demand Skill Loading**: LLM calls the `skill` tool to load full skill content only when needed (progressive disclosure)
- **Framework Agnostic**: Works with any LLM provider (OpenAI, Anthropic, MiniMaxi, local models)
- **Markdown-based Skills**: Define skills as simple Markdown files with YAML frontmatter
- **$ARGUMENTS Substitution**: Support `$ARGUMENTS`, `$1`.`$N`, `${CLAUDE_SESSION_ID}` in skill content
- **Per-Skill Model & Tools**: Each skill can specify its own `model` and `allowed-tools`
- **Context Fork**: Run skills in isolated subagent contexts with `context: fork`
- **Dynamic Content Injection**: `!`command`` syntax executes shell commands before skill content is sent to LLM
- **Description Budget**: Configurable char budget for skill descriptions in system prompt (default 16K)
- **Skill Validation**: Enforces naming rules (≤64 chars, lowercase+digits+hyphens) and description limits (≤1024 chars)
- **User-invocable Skills**: Slash commands like `/pdf`, `/pptx` for direct skill invocation
- **Eligibility Filtering**: Automatic filtering based on OS, binaries, env vars, and config
- **Environment Injection**: Securely inject API keys and env vars for skill execution
- **File Watching**: Hot-reload skills when files change
- **Multiple Sources**: Load skills from bundled, managed, workspace, and plugin directories

## Installation

```bash
# With uv (recommended)
uv add skillkit

# Basic installation
pip install skillkit

# With all dependencies
pip install skillkit[openai]
```

## Quick Start

### 1. Create `.env` file

```bash
# For MiniMaxi API (OpenAI-compatible)
OPENAI_BASE_URL=https://api.minimaxi.com/v1
OPENAI_API_KEY=your-api-key
MINIMAX_MODEL=MiniMax-M2.1

# Or for OpenAI
OPENAI_API_KEY=your-openai-key
```

### 2. Use AgentRunner (Recommended)

```python
import asyncio
from pathlib import Path
from skillkit import create_agent

async def main():
    # Create agent with automatic skill loading
    agent = await create_agent(
        skill_dirs=[Path("./skills")],
        system_prompt="You are a helpful assistant.",
        watch_skills=True,  # Hot-reload on file changes
    )

    # Chat with automatic tool execution
    response = await agent.chat("Help me create a PDF report")
    print(response.content)

    # Use slash commands
    response = await agent.chat("/pdf extract text from invoice.pdf")
    print(response.content)

asyncio.run(main())
```

### 3. Run Interactive Mode

```bash
# Run the demo
uv run python examples/agent_demo.py --interactive
```

Commands in interactive mode:
- `/skills` - List all available skills
- `/pdf`, `/pptx`, etc. - Invoke specific skills
- `/clear` - Clear conversation history
- `/quit` - Exit

## Example Skills

The `examples/skills/` directory contains ready-to-use skills:

| Skill | Description | Tools |
|-------|-------------|-------|
| **pdf** | PDF text extraction, merging, splitting, form filling | pypdf, pdfplumber, reportlab |
| **pptx** | PowerPoint creation and editing | python-pptx, markitdown |
| **algorithmic-art** | Generative art with p5.js | p5.js, HTML/JS |
| **slack-gif-creator** | Animated GIF creation for Slack | PIL/Pillow |
| **web-artifacts-builder** | React + Tailwind + shadcn/ui apps | Node.js, Vite, pnpm |

### Testing Skills

```bash
# Run all skill tests
uv run python examples/test_skills.py

# Test individual skills interactively
uv run python examples/agent_demo.py --interactive
```

## Skill Definition Format

Create `skills/my-skill/SKILL.md`:

```markdown
---
name: my-skill
description: "A helpful skill for doing things"
metadata:
  emoji: "🔧"
  requires:
    bins: ["some-cli"]
    env: ["API_KEY"]
  primary_env: "API_KEY"
user-invocable: true
---

# My Skill

Instructions for the LLM on how to use this skill...

Process: $ARGUMENTS
Current git branch: !`git branch --show-current`
```

### Skill Metadata Options

```yaml
---
name: skill-name           # Unique identifier (≤64 chars, lowercase+digits+hyphens)
description: "Brief desc"  # One-line description for LLM (≤1024 chars)

# Claude Agent Skills extensions
model: claude-sonnet-4-5-20250514  # Per-skill model override
context: fork              # "fork" to run in isolated subagent
argument-hint: "<query>"   # Autocomplete hint for slash commands
allowed-tools:             # Restrict tools available during skill execution
  - Read
  - Grep
  - Glob
hooks:                     # Per-skill lifecycle hooks
  PreToolExecution: "echo pre"
  PostToolExecution: "echo post"

metadata:
  emoji: "🔧"              # Visual indicator
  homepage: "https://..."  # Project URL
  always: false            # Always include (override eligibility)

  requires:
    bins:                  # Required binaries (ALL must exist)
      - git
      - gh
    any_bins:              # At least ONE must exist
      - npm
      - pnpm
    env:                   # Required environment variables
      - GITHUB_TOKEN
    os:                    # Supported platforms
      - darwin
      - linux

  primary_env: "API_KEY"   # Primary env var for API key injection

user-invocable: true              # Can user invoke via /skill-name
disable-model-invocation: false   # Hide from LLM system prompt
---
```

### Variable Substitution

Skill content supports dynamic placeholders:

| Placeholder | Description |
|-------------|-------------|
| `$ARGUMENTS` | Full arguments string passed to the skill |
| `$1`, `$2`, ... `$N` | Individual positional arguments (whitespace-split) |
| `${CLAUDE_SESSION_ID}` | Current session ID |
| `` !`command` `` | Replaced with command's stdout before sending to LLM |

## API Reference

### AgentRunner

```python
from skillkit import AgentRunner, AgentConfig, create_agent

# Quick creation
agent = await create_agent(
    skill_dirs=[Path("./skills")],
    system_prompt="You are helpful.",
    watch_skills=True,
)

# Or with full config
config = AgentConfig(
    model="MiniMax-M2.1",
    base_url="https://api.minimaxi.com/v1",
    api_key="...",
    max_turns=20,
    enable_tools=True,
    skill_description_budget=16000,  # Max chars for skill descriptions in system prompt
)
agent = AgentRunner(engine, config)

# Methods
response = await agent.chat("Hello")           # Single message
response = await agent.chat("/pdf help")       # Slash command
async for chunk in agent.chat_stream("Hi"):    # Streaming
    print(chunk, end="")
await agent.run_interactive()                   # Interactive mode

# Skill validation
errors = AgentRunner.validate_skill(skill)
if errors:
    print(f"Invalid skill: {errors}")
```

### Skill Tool (On-Demand Loading)

The LLM automatically gets a `skill` tool that loads full skill content on demand:

```
Tools available to LLM:
  - execute          # Run shell commands
  - execute_script   # Run multi-line scripts
  - skill            # Load skill content on demand (name, arguments)
  - <skill>:<action> # Deterministic skill actions
```

Only skill names and descriptions are in the system prompt. The LLM calls `skill(name="pdf", arguments="report.pdf")` to load the full SKILL.md content when needed.

### SkillsEngine (Low-level)

```python
from skillkit import SkillsEngine, SkillsConfig

engine = SkillsEngine(
    config=SkillsConfig(
        skill_dirs=[Path("./skills")],
        watch=True,
    )
)

# Load and filter skills
snapshot = engine.get_snapshot()
print(f"Loaded {len(snapshot.skills)} skills")
print(snapshot.prompt)  # For LLM system prompt

# Execute commands
result = await engine.execute("echo 'Hello'")
print(result.output)

# With environment injection
with engine.env_context():
    result = await engine.execute("gh pr list")
```

## Configuration

### Environment Variables

```bash
# LLM API
OPENAI_BASE_URL=https://api.minimaxi.com/v1
OPENAI_API_KEY=your-key
MINIMAX_MODEL=MiniMax-M2.1

# Or standard OpenAI
OPENAI_API_KEY=your-openai-key
```

### YAML Config

```yaml
skill_dirs:
  - ./skills
  - ~/.agent/skills

watch: true
watch_debounce_ms: 250

entries:
  github:
    enabled: true
    api_key: "ghp_..."
    env:
      GITHUB_ORG: "my-org"

prompt_format: xml  # xml, markdown, or json
default_timeout_seconds: 30
```

## Architecture

```
┌─────────────────────────────────────────────────┐
│                 AgentRunner                      │
│  - System prompt: skill names + descriptions    │
│  - Skill tool: on-demand full content loading   │
│  - $ARGUMENTS substitution + !`cmd` injection   │
│  - context: fork → isolated child agent         │
│  - Slash commands (/pdf, /pptx)                 │
│  - Per-skill model switching + tool restriction │
├─────────────────────────────────────────────────┤
│                 SkillsEngine                     │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐         │
│  │ Loader  │  │ Filter  │  │ Runtime │         │
│  └────┬────┘  └────┬────┘  └────┬────┘         │
│       │            │            │              │
│       v            v            v              │
│  ┌─────────────────────────────────────┐       │
│  │          SkillSnapshot              │       │
│  │  - skills: List[Skill]              │       │
│  │  - prompt: str (metadata only)      │       │
│  └─────────────────────────────────────┘       │
└─────────────────────────────────────────────────┘
                      │
                      v
┌─────────────────────────────────────────────────┐
│              LLM Providers                       │
│  OpenAI  │  MiniMaxi  │  Anthropic  │  Custom   │
└─────────────────────────────────────────────────┘
```

## Extending

### Custom Loader

```python
from skillkit.loaders import SkillLoader

class YAMLSkillLoader(SkillLoader):
    def can_load(self, path: Path) -> bool:
        return path.suffix == ".yaml"

    def load_skill(self, path: Path, source: SkillSource) -> SkillEntry:
        # Custom loading logic
        ...
```

### Custom Filter

```python
from skillkit.filters import SkillFilter

class TeamSkillFilter(SkillFilter):
    def filter(self, skill, config, context) -> FilterResult:
        if "team-only" in skill.metadata.tags:
            if not self.is_team_member():
                return FilterResult(skill, False, "Team members only")
        return FilterResult(skill, True)
```

### Custom Runtime

```python
from skillkit.runtime import SkillRuntime

class DockerRuntime(SkillRuntime):
    async def execute(self, command, cwd, env, timeout):
        # Execute in Docker container
        ...
```

## Development

```bash
# Clone and install
git clone https://github.com/sawzhang/skillkit.git
cd skillkit
uv sync

# Run tests
pytest

# Run skill tests
uv run python examples/test_skills.py

# Linting
ruff check src/
ruff format src/
mypy src/
```

## License

MIT License - see [LICENSE](LICENSE) for details.
