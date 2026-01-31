# Agent Skills Engine

A standalone, framework-agnostic skills execution engine for LLM agents.

## Features

- **Framework Agnostic**: Works with any LLM provider (OpenAI, Anthropic, local models)
- **Markdown-based Skills**: Define skills as simple Markdown files with YAML frontmatter
- **Eligibility Filtering**: Automatic filtering based on OS, binaries, env vars, and config
- **Environment Injection**: Securely inject API keys and env vars for skill execution
- **Multiple Sources**: Load skills from bundled, managed, workspace, and plugin directories
- **Caching & Versioning**: Efficient skill snapshot caching with change detection
- **CLI Tool**: Command-line interface for skill management and testing

## Installation

```bash
# Basic installation
pip install agent-skills-engine

# With uv (recommended)
uv add agent-skills-engine

# With OpenAI adapter
pip install agent-skills-engine[openai]

# With Anthropic adapter
pip install agent-skills-engine[anthropic]

# Development
pip install agent-skills-engine[dev]
```

## Quick Start

### 1. Define a Skill

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
---

# My Skill

Instructions for the LLM on how to use this skill...
```

### 2. Use the Engine

```python
from agent_skills_engine import SkillsEngine, SkillsConfig
from pathlib import Path

# Initialize
engine = SkillsEngine(
    config=SkillsConfig(
        skill_dirs=[Path("./skills")],
    )
)

# Get eligible skills
snapshot = engine.get_snapshot()
print(f"Loaded {len(snapshot.skills)} skills")

# Get prompt for LLM
print(snapshot.prompt)

# Execute a command
result = await engine.execute("echo 'Hello, World!'")
print(result.output)
```

### 3. With LLM Adapters

```python
from openai import AsyncOpenAI
from agent_skills_engine import SkillsEngine
from agent_skills_engine.adapters import OpenAIAdapter

engine = SkillsEngine(config=...)
adapter = OpenAIAdapter(engine, AsyncOpenAI())

# Skills are automatically injected into system prompt
response = await adapter.chat([
    Message(role="user", content="List my GitHub PRs")
])
```

## Skill Definition Format

Skills are Markdown files with YAML frontmatter:

```yaml
---
name: skill-name           # Unique identifier
description: "Brief desc"  # One-line description for LLM

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
      - yarn
    env:                   # Required environment variables
      - GITHUB_TOKEN
    os:                    # Supported platforms
      - darwin
      - linux

  primary_env: "API_KEY"   # Primary env var for API key injection

  install:                 # Installation instructions
    - kind: brew
      id: gh
      bins: ["gh"]

user-invocable: true              # Can user invoke via /skill-name
disable-model-invocation: false   # Hide from LLM system prompt
---

# Skill Content

Detailed instructions for the LLM...
```

## Configuration

### YAML Config

```yaml
skill_dirs:
  - ./skills
  - ~/.agent/skills

bundled_dir: /usr/share/agent/skills
managed_dir: ~/.agent/managed-skills

allow_bundled:
  - github
  - shell

watch: true
watch_debounce_ms: 250

entries:
  github:
    enabled: true
    api_key: "ghp_..."
    env:
      GITHUB_ORG: "my-org"

  private-skill:
    enabled: false

prompt_format: xml  # xml, markdown, or json
default_timeout_seconds: 30
```

### Programmatic Config

```python
from agent_skills_engine import SkillsConfig, SkillEntryConfig

config = SkillsConfig(
    skill_dirs=[Path("./skills")],
    allow_bundled=["github", "shell"],
    entries={
        "github": SkillEntryConfig(
            enabled=True,
            api_key="ghp_...",
        ),
    },
)
```

## CLI Usage

```bash
# List skills
skills list -d ./skills

# Show skill details
skills show github -d ./skills

# Generate prompt
skills prompt -d ./skills -f xml

# Execute command
skills exec echo "hello"
```

## Architecture

```
┌─────────────────────────────────────────┐
│              SkillsEngine               │
├─────────────────────────────────────────┤
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  │
│  │ Loader  │  │ Filter  │  │ Runtime │  │
│  └────┬────┘  └────┬────┘  └────┬────┘  │
│       │            │            │       │
│       v            v            v       │
│  ┌─────────────────────────────────┐   │
│  │         SkillSnapshot           │   │
│  │  - skills: List[Skill]          │   │
│  │  - prompt: str                  │   │
│  │  - version: int                 │   │
│  └─────────────────────────────────┘   │
└─────────────────────────────────────────┘
                    │
                    v
┌─────────────────────────────────────────┐
│            LLM Adapters                 │
├─────────────────────────────────────────┤
│  OpenAI  │  Anthropic  │  Custom...     │
└─────────────────────────────────────────┘
```

## Extending

### Custom Loader

```python
from agent_skills_engine.loaders import SkillLoader

class YAMLSkillLoader(SkillLoader):
    def can_load(self, path: Path) -> bool:
        return path.suffix == ".yaml"

    def load_skill(self, path: Path, source: SkillSource) -> SkillEntry:
        # Custom loading logic
        ...
```

### Custom Filter

```python
from agent_skills_engine.filters import SkillFilter

class TeamSkillFilter(SkillFilter):
    def filter(self, skill, config, context) -> FilterResult:
        # Custom eligibility logic
        if skill.metadata.tags and "team-only" in skill.metadata.tags:
            if not self.is_team_member():
                return FilterResult(skill, False, "Team members only")
        return FilterResult(skill, True)
```

### Custom Runtime

```python
from agent_skills_engine.runtime import SkillRuntime

class DockerRuntime(SkillRuntime):
    async def execute(self, command, cwd, env, timeout):
        # Execute in Docker container
        ...
```

## License

MIT License - see [LICENSE](LICENSE) for details.

## Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.
