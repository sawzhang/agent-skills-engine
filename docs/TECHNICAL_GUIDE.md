# SkillKit - 技术架构文档

> **Skills are new software. CLIs are new API. Agents are new OS.**

---

## 目录

1. [设计哲学：Skill First](#1-设计哲学skill-first)
2. [整体架构概览](#2-整体架构概览)
3. [核心体系详解](#3-核心体系详解)
   - [3.1 Skills 技能体系](#31-skills-技能体系)
   - [3.2 Agent 代理体系](#32-agent-代理体系)
   - [3.3 Tools 工具体系](#33-tools-工具体系)
   - [3.4 Memory 记忆体系](#34-memory-记忆体系)
   - [3.5 MCP / Extensions 扩展体系](#35-mcp--extensions-扩展体系)
4. [支撑体系](#4-支撑体系)
   - [4.1 事件总线 (EventBus)](#41-事件总线-eventbus)
   - [4.2 上下文管理 (ContextManager)](#42-上下文管理-contextmanager)
   - [4.3 会话持久化 (Session)](#43-会话持久化-session)
   - [4.4 包管理 (Packages)](#44-包管理-packages)
   - [4.5 跨模型适配 (Adapters)](#45-跨模型适配-adapters)
5. [完整执行流程：Skill 的动态加载与运行](#5-完整执行流程skill-的动态加载与运行)
6. [与其他 Agent 哲学的对比](#6-与其他-agent-哲学的对比)

---

## 1. 设计哲学：Skill First

### 什么是 Skill First？

在 Agent 系统的四大哲学中，**Skill First（技能/扩展优先）** 代表了一种极简主义路线：

| 维度 | Skill First 的做法 |
|------|-------------------|
| **原语工具** | 只给 Agent 极少的内置工具（4 个：execute, execute_script, read, write） |
| **能力来源** | 所有高级能力外包给 Skill 文件/扩展，而非硬编码为 tool |
| **Prompt 策略** | Prompt 极短，靠 caching + 模型推理 |
| **自主性** | 高（裸 ReAct loop，几乎完全靠模型自己推理/决定何时结束） |
| **适用场景** | 极简、高效 token、省钱、coding agent 场景最强 |

### 核心理念

```
传统做法:  给 Agent 100 个 tools → 模型选择困难 → token 爆炸 → 推理混乱
Skill First: 给 Agent 4 个原语 + 动态注入的 Skill prompt → 模型自由推理 → 高效精准
```

**关键洞察**：Skill 不是 function calling 的 tool，而是注入到 system prompt 中的**指导知识**。LLM 读取 Skill 内容后，使用少量内置工具（主要是 bash）来完成任务。这就是为什么叫 "Skills are new software" — Skill 本质上是给 Agent 的"软件说明书"。

---

## 2. 整体架构概览

```
┌─────────────────────────────────────────────────────────────────────┐
│                        用户交互层                                    │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐           │
│  │ CLI/TUI  │  │  Web UI  │  │ RPC Mode │  │ JSON Mode│           │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘           │
│       └──────────────┴──────────────┴──────────────┘                │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────────────┐
│                      AgentRunner（代理运行器）                        │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────┐               │
│  │ EventBus    │  │ContextManager│  │SessionManager│               │
│  │ (事件总线)  │  │ (上下文管理) │  │ (会话持久化) │               │
│  └─────────────┘  └──────────────┘  └──────────────┘               │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────────────┐
│                      SkillsEngine（技能引擎）                        │
│                                                                     │
│  Skill Files ──→ [Loader] ──→ [Filter] ──→ [Snapshot] ──→ Prompt  │
│  (SKILL.md)     解析技能      资格检查      缓存快照     注入LLM   │
│                                                                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐           │
│  │ Markdown │  │ Default  │  │   Bash   │  │ OpenAI / │           │
│  │ Loader   │  │ Filter   │  │ Runtime  │  │ Anthropic│           │
│  └──────────┘  └──────────┘  └──────────┘  │ Adapter  │           │
│                                             └──────────┘           │
└─────────────────────────────────────────────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────────────┐
│                         外部体系                                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐           │
│  │ Memory   │  │Extensions│  │ Packages │  │ Context  │           │
│  │(OpenViking)│ │ (插件)  │  │ (包管理) │  │  Files   │           │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘           │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 3. 核心体系详解

### 3.1 Skills 技能体系

Skills 是整个系统的核心。每个 Skill 是一个 Markdown 文件 + YAML 前言，描述了 Agent 的一种能力。

#### 3.1.1 Skill 定义格式

```yaml
# skills/github/SKILL.md
---
name: github
description: "Interact with GitHub repositories, issues, and PRs using the gh CLI"
metadata:
  emoji: "🐙"
  homepage: "https://cli.github.com"
  author: "Alex Zhang"
  version: "1.0.0"
  tags: ["git", "devops"]
  primary_env: "GITHUB_TOKEN"        # 主要 API Key 环境变量
  requires:
    bins: ["gh"]                      # 所有必须存在的二进制
    any_bins: ["npm", "pnpm"]         # 至少一个存在
    env: ["GITHUB_TOKEN"]             # 必须的环境变量
    os: ["darwin", "linux"]           # 支持的操作系统
  install:
    - kind: brew
      id: gh
      label: "GitHub CLI (Homebrew)"
      bins: ["gh"]
      os: ["darwin", "linux"]
  invocation:
    user_invocable: true              # 用户可通过 /github 直接调用
    disable_model_invocation: false   # 不从 LLM system prompt 隐藏
    require_confirmation: false       # 执行前不需确认
actions:
  create-issue:
    script: "scripts/create-issue.sh"
    description: "Create a new GitHub issue"
    output: "json"
    params:
      - name: title
        type: string
        required: true
        position: 1
      - name: body
        type: string
        required: false
---
# GitHub CLI Skill

You have access to the GitHub CLI (`gh`).
Use it to manage repositories, issues, pull requests, and more.

## Common Operations

- List issues: `gh issue list`
- Create PR: `gh pr create --title "..." --body "..."`
- View PR status: `gh pr status`

## Best Practices

- Always check `gh auth status` before operations
- Use `--json` flag for structured output
```

#### 3.1.2 Skill 数据模型

```python
@dataclass
class Skill:
    name: str                    # 唯一标识符
    description: str             # 一行描述（给 LLM 看）
    content: str                 # 完整内容（注入 system prompt）
    file_path: Path              # SKILL.md 的完整路径
    base_dir: Path               # 父目录（用于相对路径解析）
    source: SkillSource          # 来源：BUNDLED / MANAGED / WORKSPACE / PLUGIN / EXTRA
    metadata: SkillMetadata      # 扩展元数据
    actions: dict[str, SkillAction]  # 确定性动作（脚本）

    def content_hash(self) -> str:
        """SHA256 哈希，用于缓存失效检测"""
        return hashlib.sha256(self.content.encode()).hexdigest()[:16]
```

#### 3.1.3 Skill 来源优先级

```
BUNDLED (内置)  →  MANAGED (~/.agent/skills)  →  WORKSPACE (./skills)  →  EXTRA (额外目录)
        低优先级                                                              高优先级
```

后加载的目录覆盖先加载的同名 Skill，实现用户自定义覆盖内置行为。

#### 3.1.4 Skill 加载 → 过滤 → 快照

```
                ┌──────────────────────────────────────────────┐
                │               MarkdownSkillLoader            │
                │                                              │
SKILL.md ──────→│ 1. 读取文件                                 │
                │ 2. 分离 YAML frontmatter 和 Markdown body   │
                │ 3. 解析 metadata, requirements, actions      │
                │ 4. 构建 Skill 对象                          │
                └──────────────┬───────────────────────────────┘
                               │
                ┌──────────────▼───────────────────────────────┐
                │              DefaultSkillFilter               │
                │                                              │
                │ 短路检查（按序，首个失败即跳过该 Skill）：    │
                │ 1. always=true? → 直接通过                   │
                │ 2. 配置中 enabled=false? → 排除              │
                │ 3. 在 exclude_skills 列表中? → 排除          │
                │ 4. 在 bundled allowlist 中? → 检查            │
                │ 5. OS 匹配? (darwin/linux/win32)             │
                │ 6. 所有 bins 存在? (which 检查)              │
                │ 7. any_bins 至少一个存在?                     │
                │ 8. 环境变量存在? (多级查找)                   │
                │ 9. 配置路径存在?                              │
                └──────────────┬───────────────────────────────┘
                               │
                ┌──────────────▼───────────────────────────────┐
                │              SkillSnapshot                    │
                │                                              │
                │ skills: list[Skill]    # 合格的技能列表       │
                │ prompt: str            # 预格式化的 LLM prompt │
                │ version: int           # 版本号（缓存失效）   │
                │ timestamp: float       # 创建时间戳           │
                └──────────────────────────────────────────────┘
```

#### 3.1.5 Prompt 格式化

Skill 内容可以格式化为三种格式注入 LLM system prompt：

**XML 格式（默认，最适合 LLM 解析）：**
```xml
<skills>
  <skill name="github" emoji="🐙">
    <description>Interact with GitHub using gh CLI</description>
    <content>
      You have access to the GitHub CLI...
    </content>
  </skill>
</skills>
```

**Markdown 格式（人类可读）：**
```markdown
## 🐙 github
Interact with GitHub using gh CLI

You have access to the GitHub CLI...
```

**JSON 格式（程序化处理）：**
```json
[{"name": "github", "description": "...", "content": "..."}]
```

---

### 3.2 Agent 代理体系

AgentRunner 是最上层的编排器，实现了完整的 ReAct 循环。

#### 3.2.1 Agent 配置

```python
@dataclass
class AgentConfig:
    # LLM 设置
    model: str = "MiniMax-M2.1"
    base_url: str | None = None       # 默认读取 OPENAI_BASE_URL
    api_key: str | None = None        # 默认读取 OPENAI_API_KEY
    temperature: float = 0.0
    max_tokens: int = 8192

    # Agent 行为
    max_turns: int = 50               # 最大工具调用轮次
    enable_tools: bool = True         # 启用 function calling
    enable_reasoning: bool = False    # 启用推理模式
    auto_execute: bool = True         # 自动执行工具调用

    # 思考 & 传输
    thinking_level: ThinkingLevel | None = None   # off/short/long/extended
    transport: Transport = "sse"

    # Skills
    skill_dirs: list[Path] = []       # 技能目录
    watch_skills: bool = False        # 监听文件变化热重载
    system_prompt: str = ""           # 基础系统提示

    # 缓存 & 上下文
    cache_retention: str = "none"     # none/short/long
    session_id: str | None = None     # 会话 ID
    load_context_files: bool = True   # 自动发现 AGENTS.md / CLAUDE.md
```

#### 3.2.2 Agent 执行循环（ReAct Loop）

```
用户输入
  │
  ▼
┌─────────────────────────────────────────────────┐
│ 1. INPUT 事件 → 可转换/拦截/直接处理            │
│ 2. 检查 /skill-name 调用 → 如果是则注入 skill   │
│ 3. 构建消息列表 (system prompt + history + user) │
│ 4. 触发 AGENT_START 事件                        │
└────────────────────┬────────────────────────────┘
                     │
          ┌──────────▼──────────┐
          │ TURN_START 事件     │◄──────────────────┐
          │ 检查上下文压缩      │                    │
          │ 触发 CONTEXT_TRANSFORM │                 │
          │ 调用 LLM            │                    │
          └──────────┬──────────┘                    │
                     │                               │
          ┌──────────▼──────────┐                    │
          │ LLM 返回响应        │                    │
          │ TURN_END 事件       │                    │
          └──────────┬──────────┘                    │
                     │                               │
              有 tool_calls?                         │
             ┌──YES──┴──NO──┐                        │
             │              │                        │
    ┌────────▼────────┐     │                        │
    │ BEFORE_TOOL_CALL│     ▼                        │
    │ → 可阻止/修改   │  返回最终响应                │
    │ 执行工具         │  AGENT_END 事件             │
    │ AFTER_TOOL_RESULT│                             │
    │ → 可修改结果     │                             │
    │ 检查 steering    │                             │
    │ 检查 follow_up   │                             │
    └────────┬────────┘                              │
             │                                       │
             │  turn < max_turns?                    │
             └──────────YES──────────────────────────┘
```

#### 3.2.3 流式响应

AgentRunner 提供三种响应模式：

```python
# 1. 同步等待完整响应
response = await agent.chat("Fix the bug in auth.py")

# 2. 流式文本增量
async for delta in agent.chat_stream("Explain this code"):
    print(delta, end="")

# 3. 结构化事件流（最强大）
async for event in agent.chat_stream_events("Refactor this"):
    match event.type:
        case "text_start":     ...  # 文本开始
        case "text_delta":     ...  # 文本增量
        case "text_end":       ...  # 文本结束
        case "thinking_start": ...  # 思考开始
        case "thinking_delta": ...  # 思考增量
        case "tool_call_start":...  # 工具调用开始
        case "tool_call_delta":...  # 参数增量（流式 JSON）
        case "tool_call_end":  ...  # 工具调用结束
        case "tool_result":    ...  # 工具执行结果
        case "turn_start":     ...  # 新轮次开始
        case "turn_end":       ...  # 轮次结束
        case "done":           ...  # 完全结束
        case "error":          ...  # 错误
```

#### 3.2.4 中断与转向

```python
# 中止正在运行的操作
agent.abort()

# 转向：注入新指令，中止当前工具执行
agent.steer("Stop that, focus on the tests instead")

# 后续追加：在当前循环结束后追加消息
agent.follow_up("Also run the linter")
```

---

### 3.3 Tools 工具体系

Skill First 哲学的关键：**只有极少的内置工具，所有高级能力来自 Skills。**

#### 3.3.1 内置工具（仅 4 个原语）

这是 Agent 通过 function calling 可以调用的工具：

| 工具 | 功能 | 说明 |
|------|------|------|
| `execute` | 执行单条 bash 命令 | 带超时、流式输出、中止支持 |
| `execute_script` | 执行多行脚本 | 通过临时文件执行 |
| `read` | 读取文件 | 支持文本/图片/行范围 |
| `write` | 写入文件 | 自动创建目录 |

**为什么只有 4 个？** 因为 bash 可以做任何事。与其给模型 100 个 API wrapper tool，不如让模型通过 Skill 里的知识学会用 bash 调用 CLI。这就是 "CLIs are new API" 的精髓。

#### 3.3.2 扩展工具集

通过 `ToolRegistry` 可以注册额外工具，但它们不是 function calling tool，而是给 TUI/CLI 使用：

```python
# 编程工具集（用于 coding agent）
create_coding_tools()  # → Read, Write, Edit, Bash

# 只读工具集（用于分析/搜索）
create_read_only_tools()  # → Read, Grep, Find, Ls

# 完整工具集
create_all_tools()  # → Read, Write, Edit, Bash, Grep, Find, Ls
```

| 工具 | 功能 |
|------|------|
| `BashTool` | Shell 执行，100K 字符限制，120s 超时 |
| `ReadTool` | 读文件（cat -n 格式），支持 base64 图片 |
| `WriteTool` | 写文件，自动创建父目录 |
| `EditTool` | 精确字符串替换，支持 replace_all |
| `FindTool` | Glob 模式匹配，尊重 .gitignore |
| `GrepTool` | 正则搜索，优先用 ripgrep 加速 |
| `LsTool` | 目录列表，递归限 1000 条 |

#### 3.3.3 工具执行流程

```python
# Agent 调用 execute tool 时的执行路径
async def _execute_tool(self, tool_call, on_output):
    name = tool_call["function"]["name"]
    args = json.loads(tool_call["function"]["arguments"])

    match name:
        case "execute":
            result = await self.engine.execute(
                command=args["command"],
                timeout=args.get("timeout", 120),
                on_output=on_output,      # 流式输出回调
                abort_signal=self._abort,  # 中止信号
            )
        case "execute_script":
            result = await self.engine.execute_script(
                script=args["script"],
                timeout=args.get("timeout", 120),
            )
        case _:
            # 扩展工具分发
            result = await extension_manager.dispatch(name, args)

    return result.output if result.success else f"Error: {result.error}"
```

---

### 3.4 Memory 记忆体系

基于 OpenViking 上下文数据库实现的跨会话持久化记忆。

#### 3.4.1 架构

```
┌───────────────────────────────────────────────────────┐
│                    AgentRunner                         │
│                                                       │
│  ┌───────────────┐  ┌──────────────────────────────┐ │
│  │   EventBus    │  │     Extension Manager        │ │
│  │               │  │                              │ │
│  │ AGENT_START ──┼──┼→ MemoryHooks.on_agent_start │ │
│  │ CONTEXT_TRANSFORM┼→ MemoryHooks.on_context_transform │
│  │ AGENT_END ────┼──┼→ MemoryHooks.on_agent_end   │ │
│  └───────────────┘  │                              │ │
│                     │  Memory Tools:               │ │
│                     │  ├─ recall_memory            │ │
│                     │  ├─ save_memory              │ │
│                     │  ├─ explore_memory           │ │
│                     │  └─ add_knowledge            │ │
│                     └──────────────┬───────────────┘ │
└────────────────────────────────────┼─────────────────┘
                                     │ HTTP
                          ┌──────────▼──────────┐
                          │   OpenViking Server  │
                          │  (上下文数据库)       │
                          │  localhost:1933       │
                          └──────────────────────┘
```

#### 3.4.2 配置

```python
@dataclass
class MemoryConfig:
    base_url: str = "http://localhost:1933"
    api_key: str | None = None
    timeout: float = 30.0
    auto_session: bool = True     # AGENT_START 时自动创建 session
    auto_sync: bool = True        # 压缩/结束时自动同步消息
    auto_commit: bool = True      # AGENT_END 时触发知识提取
    default_search_limit: int = 5
```

#### 3.4.3 记忆工具

LLM 可以通过 function calling 使用以下 4 个记忆工具：

```python
# 1. 回忆记忆 — 搜索历史对话和知识
recall_memory(query="用户的编码偏好", scope="user", limit=5)
# → 返回匹配的记忆片段

# 2. 保存记忆 — 持久化重要信息
save_memory(content="用户偏好 Python type hints", category="preferences")
# → 保存到 OpenViking

# 3. 浏览记忆 — 文件系统式浏览
explore_memory(uri="/users/sawzhang/preferences", recursive=True)
# → 返回记忆树结构

# 4. 添加知识 — 索引本地文件
add_knowledge(path="/path/to/design-doc.md", reason="项目架构参考")
# → 将文件内容索引到记忆库
```

#### 3.4.4 生命周期钩子

```python
class MemoryHooks:
    async def on_agent_start(self, event: AgentStartEvent):
        """创建 OpenViking 会话"""
        self.state.session_id = await self.client.create_session(
            cwd=os.getcwd(),
            model=event.model,
        )

    async def on_context_transform(self, event: ContextTransformEvent):
        """同步新消息到 OpenViking（用于上下文压缩时保留记忆）"""
        new_messages = event.messages[self._synced_count:]
        for msg in new_messages:
            await self.client.add_message(self.state.session_id, msg)
        self._synced_count = len(event.messages)

    async def on_agent_end(self, event: AgentEndEvent):
        """同步剩余消息 + 触发知识提取"""
        await self._sync_remaining()
        await self.client.commit_session(self.state.session_id)
```

---

### 3.5 MCP / Extensions 扩展体系

Extensions 提供插件式扩展，可以注册工具、命令和生命周期钩子。

#### 3.5.1 扩展 API

```python
class ExtensionAPI:
    """扩展可以使用的 API"""
    def register_tool(self, tool_info: ToolInfo): ...
    def register_command(self, command_info: CommandInfo): ...
    def get_event_bus(self) -> EventBus: ...
    def get_engine(self) -> SkillsEngine: ...
```

#### 3.5.2 工具注册

```python
class ToolInfo:
    name: str                    # 工具名称
    description: str             # 功能描述
    parameters: dict             # JSON Schema 参数定义
    handler: Callable            # 异步处理函数

# 注册自定义工具示例
api.register_tool(ToolInfo(
    name="search_docs",
    description="Search project documentation",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"}
        },
        "required": ["query"]
    },
    handler=my_search_handler
))
```

#### 3.5.3 命令注册

```python
class CommandInfo:
    name: str               # 命令名（如 "status"）
    description: str        # 描述
    handler: Callable       # 处理函数
    source: str             # 来源标识

# 注册 /status 命令
api.register_command(CommandInfo(
    name="status",
    description="Show project status",
    handler=status_handler,
    source="my-extension"
))
```

#### 3.5.4 Memory 作为 Extension 的接入示例

```python
def setup_memory(agent: AgentRunner, config: MemoryConfig) -> OpenVikingClient | None:
    """将 Memory 系统作为 Extension 接入 Agent"""
    # 1. 创建客户端并检查可用性
    client = OpenVikingClient(config.base_url, config.api_key)
    if not await client.available:
        return None

    # 2. 初始化扩展管理器
    ext_manager = agent.engine.init_extensions()

    # 3. 注册 4 个记忆工具
    state = MemoryState(client=client)
    ext_manager.register_tool(make_recall_tool(state))
    ext_manager.register_tool(make_save_tool(state))
    ext_manager.register_tool(make_explore_tool(state))
    ext_manager.register_tool(make_knowledge_tool(state))

    # 4. 注册 3 个生命周期钩子
    hooks = MemoryHooks(client, state)
    bus = agent.events
    bus.on(AGENT_START, hooks.on_agent_start, priority=10)
    bus.on(CONTEXT_TRANSFORM, hooks.on_context_transform, priority=100)
    bus.on(AGENT_END, hooks.on_agent_end, priority=90)

    return client
```

---

## 4. 支撑体系

### 4.1 事件总线 (EventBus)

所有生命周期事件通过 EventBus 传播，支持拦截和修改。

```python
class EventBus:
    def on(self, event: str, handler, priority: int = 0, source: str = ""): ...
    async def emit(self, event: str, data) -> list[Any]: ...
```

**完整事件列表：**

| 事件 | 触发时机 | 可做的事 |
|------|---------|---------|
| `AGENT_START` | Agent 开始处理请求 | 初始化资源、创建 session |
| `AGENT_END` | Agent 完成（含 finish_reason） | 清理资源、提交记忆 |
| `TURN_START` | 每次调用 LLM 前 | 记录轮次信息 |
| `TURN_END` | LLM 返回后 | 分析响应、记录统计 |
| `BEFORE_TOOL_CALL` | 工具执行前 | **阻止**执行、修改参数 |
| `AFTER_TOOL_RESULT` | 工具执行后 | 修改结果、记录审计 |
| `CONTEXT_TRANSFORM` | 发送给 LLM 前 | 注入/删减消息、压缩上下文 |
| `INPUT` | 用户输入时 | 转换输入、直接处理（跳过 LLM） |
| `TOOL_EXECUTION_UPDATE` | 工具实时输出 | 流式展示进度 |
| `SESSION_START/END` | 会话生命周期 | 持久化管理 |
| `MODEL_CHANGE` | 切换模型时 | 记录变更 |
| `COMPACTION` | 上下文压缩时 | 同步记忆 |

**事件拦截示例：**

```python
# 阻止危险命令执行
@bus.on(BEFORE_TOOL_CALL, priority=0)
async def guard(event: BeforeToolCallEvent):
    if "rm -rf" in event.args.get("command", ""):
        return ToolCallEventResult(block=True, reason="Dangerous command blocked")

# 注入上下文信息
@bus.on(CONTEXT_TRANSFORM, priority=50)
async def inject_context(event: ContextTransformEvent):
    messages = list(event.messages)
    messages.insert(1, AgentMessage(role="system", content="Remember: use Python 3.12"))
    return ContextTransformEventResult(messages=messages)
```

---

### 4.2 上下文管理 (ContextManager)

管理 LLM 上下文窗口预算，防止超出限制。

```python
class ContextManager:
    context_window: int = 128_000    # 模型上下文窗口
    reserve_tokens: int = 4096       # 输出预留
    threshold: float = 0.9           # 触发压缩的阈值

    def should_compact(self, messages) -> bool: ...
    async def compact(self, messages) -> list[AgentMessage]: ...
```

**压缩策略：**

1. **TokenBudgetCompactor**（默认）：从最早的消息开始删除，直到 fit 预算
2. **SlidingWindowCompactor**：保留最近 N 轮对话，删除更早的

```
[sys] [u1] [a1] [u2] [a2] [u3] [a3] [u4] [a4]  ← 超出预算
                              ↓ TokenBudget 压缩
[sys]                    [u3] [a3] [u4] [a4]      ← fit 预算
```

---

### 4.3 会话持久化 (Session)

基于 JSONL 的会话存储，支持分支树结构。

#### 4.3.1 存储格式

```
~/.skillkit/sessions/{cwd-hash-16}/
  └── {session-id}.jsonl
```

每个 `.jsonl` 文件：
```json
{"type": "header", "id": "h1", "version": 1, "cwd": "/project", "timestamp": 1708000000}
{"type": "message", "id": "m1", "parent_id": "h1", "role": "user", "content": "Fix the bug"}
{"type": "message", "id": "m2", "parent_id": "m1", "role": "assistant", "content": "I'll fix..."}
{"type": "compaction", "id": "c1", "parent_id": "m2", "summary": "...", "tokens_before": 50000, "tokens_after": 12000}
```

#### 4.3.2 分支 (Fork)

```
       h1 ─── m1 ─── m2 ─── m3 ─── m4  (主线)
                        │
                        └── m5 ─── m6    (分支：从 m2 分叉)
```

```python
# 从某个消息点分叉新会话
new_session = session_manager.fork(entry_id="m2")
# 创建新 .jsonl 文件，包含 parent_session 指针
```

---

### 4.4 包管理 (Packages)

发现和加载来自多个来源的 Skills、Extensions、Themes、Prompts。

```python
class PackageManager:
    user_dir = ~/.skillkit/packages/     # 用户级
    project_dir = ./.skillkit/packages/  # 项目级

    def resolve(self, sources=None) -> list[ResolvedPackage]:
        """自动发现 + 显式来源"""
        ...
```

**来源类型：**
- `local`: 本地路径 (`./my-skills/`)
- `pypi`: Python 包 (`my-skill-pack`)
- `git`: Git 仓库 (`git+https://github.com/user/skills.git`)

**Manifest 格式 (`pyproject.toml`)：**
```toml
[tool.skillkit]
skills = ["skills/**"]
extensions = ["ext/**/*.py"]
themes = ["themes/*.yaml"]
prompts = ["prompts/*.md"]
```

---

### 4.5 跨模型适配 (Adapters)

支持在 OpenAI 和 Anthropic 之间无缝切换。

```python
class AdapterRegistry:
    """管理多个 LLM 适配器"""
    adapters: dict[str, LLMAdapter]

    def register(self, name: str, adapter: LLMAdapter): ...
    def get(self, name: str) -> LLMAdapter: ...
```

**消息转换：**

```python
# OpenAI → Anthropic 的自动转换
transform_messages(messages, target_provider="anthropic", source_provider="openai")

# 处理差异：
# 1. Tool call ID 长度：OpenAI 450+ chars → Anthropic max 64 (SHA-256 截断)
# 2. Thinking blocks：Anthropic 原生 → OpenAI 转为 text 前缀
# 3. 孤立 tool calls：自动插入合成的空 tool result
# 4. 错误消息：跳过空内容 + 无 tool_calls 的 assistant 消息
```

---

## 5. 完整执行流程：Skill 的动态加载与运行

以下是用户发出 "帮我创建一个 GitHub Issue" 这个请求后，系统从头到尾的完整流程：

### 阶段 1：初始化

```python
# 创建 Agent
agent = await create_agent(
    skill_dirs=[
        Path("~/.skillkit/skills"),   # 用户全局技能
        Path("./skills"),                  # 项目本地技能
    ],
    system_prompt="You are a helpful coding assistant.",
    model="claude-sonnet-4-20250514",
)
```

**内部执行：**
```
1. AgentRunner.__init__()
   ├─ 创建 SkillsEngine(config, loader, filter, runtime)
   │   ├─ loader = MarkdownSkillLoader()
   │   ├─ filter = DefaultSkillFilter()
   │   └─ runtime = BashRuntime(shell="/bin/bash", timeout=30s)
   ├─ 创建 EventBus()
   ├─ 创建 ContextManager(context_window=200000)
   └─ 加载 context files (AGENTS.md, CLAUDE.md)

2. setup_memory(agent, memory_config)  [可选]
   ├─ 创建 OpenVikingClient → 健康检查
   ├─ 注册 4 个 memory tools
   └─ 注册 3 个 lifecycle hooks
```

### 阶段 2：Skill 动态加载

```
engine.get_snapshot()
  │
  ├─ engine.load_skills()
  │   │
  │   ├─ 扫描 ~/.skillkit/skills/
  │   │   ├─ github/SKILL.md  → MarkdownSkillLoader.load_skill()
  │   │   │   ├─ 读取文件内容
  │   │   │   ├─ 分离 YAML frontmatter
  │   │   │   ├─ 解析 metadata: emoji="🐙", requires.bins=["gh"], requires.env=["GITHUB_TOKEN"]
  │   │   │   ├─ 解析 actions: create-issue → scripts/create-issue.sh
  │   │   │   └─ 返回 Skill(name="github", source=MANAGED, ...)
  │   │   │
  │   │   ├─ docker/SKILL.md  → Skill(name="docker", ...)
  │   │   └─ python/SKILL.md  → Skill(name="python", ...)
  │   │
  │   └─ 扫描 ./skills/
  │       └─ my-tool/SKILL.md → Skill(name="my-tool", source=WORKSPACE, ...)
  │
  ├─ engine.filter_skills(all_skills, context)
  │   │
  │   ├─ github: ✓ bins=["gh"] 存在, ✓ env=["GITHUB_TOKEN"] 存在 → 合格
  │   ├─ docker: ✗ bins=["docker"] 不存在 → 排除 (reason: "missing binary: docker")
  │   ├─ python: ✓ → 合格
  │   └─ my-tool: ✓ → 合格
  │
  ├─ engine.format_prompt([github, python, my-tool], format="xml")
  │   └─ 生成 XML 格式的技能提示
  │
  └─ 返回 SkillSnapshot(
       skills=[github, python, my-tool],
       prompt="<skills>...",
       version=1,
       timestamp=1708000000
     )
```

### 阶段 3：构建 System Prompt

```python
agent.build_system_prompt()
```

```
最终 system prompt =
  基础系统提示 (system_prompt)
  + Context Files 内容 (AGENTS.md / CLAUDE.md)
  + Skills Prompt:
    <skills>
      <skill name="github" emoji="🐙">
        <description>Interact with GitHub using gh CLI</description>
        <content>
          You have access to the GitHub CLI...
          ## Common Operations
          - List issues: `gh issue list`
          - Create PR: `gh pr create --title "..." --body "..."`
          ...
        </content>
      </skill>
      <skill name="python">...</skill>
      <skill name="my-tool">...</skill>
    </skills>
```

### 阶段 4：用户请求处理

```python
response = await agent.chat("帮我创建一个 GitHub Issue，标题是 'Fix login bug'")
```

**详细流程：**

```
Step 1: INPUT 事件
  ├─ emit(INPUT, InputEvent(user_input="帮我创建一个 GitHub Issue..."))
  ├─ 检查是否 /skill-name 调用 → 不是
  └─ 添加 user message 到 history

Step 2: AGENT_START 事件
  ├─ emit(AGENT_START, AgentStartEvent(user_input=..., model="claude-sonnet-4-20250514"))
  └─ MemoryHooks.on_agent_start → 创建 OpenViking session

Step 3: Turn 1 - 调用 LLM
  ├─ TURN_START(turn=1, message_count=3)
  │
  ├─ 检查上下文是否需要压缩 → context_manager.should_compact() → No
  │
  ├─ CONTEXT_TRANSFORM → MemoryHooks 同步消息
  │
  ├─ _call_llm(messages=[system, user], stream=True)
  │   └─ Anthropic API 调用，带 tools=[execute, execute_script, read, write]
  │
  ├─ LLM 响应:
  │   content: "我来帮你创建这个 GitHub Issue。"
  │   tool_calls: [{
  │     id: "call_001",
  │     function: {
  │       name: "execute",
  │       arguments: '{"command": "gh issue create --title \"Fix login bug\" --body \"...\"", "timeout": 30}'
  │     }
  │   }]
  │
  └─ TURN_END(turn=1, has_tool_calls=true, tool_call_count=1)

Step 4: 工具执行
  ├─ BEFORE_TOOL_CALL(tool_name="execute", args={command: "gh issue create ..."})
  │   └─ 无拦截 → 继续执行
  │
  ├─ _execute_tool(tool_call)
  │   ├─ engine.execute(command="gh issue create ...", timeout=30)
  │   │   └─ BashRuntime.execute()
  │   │       ├─ 创建 subprocess: /bin/bash -c "gh issue create ..."
  │   │       ├─ 流式读取 stdout/stderr
  │   │       ├─ 进程退出 exit_code=0
  │   │       └─ 返回 ExecutionResult(
  │   │            success=true,
  │   │            output="https://github.com/user/repo/issues/42",
  │   │            exit_code=0,
  │   │            duration_ms=1523
  │   │          )
  │   └─ 返回 "https://github.com/user/repo/issues/42"
  │
  └─ AFTER_TOOL_RESULT(tool_name="execute", result="https://...")
      └─ 结果添加到 history 作为 tool message

Step 5: Turn 2 - LLM 处理工具结果
  ├─ TURN_START(turn=2)
  │
  ├─ _call_llm(messages=[system, user, assistant+tool_calls, tool_result])
  │
  ├─ LLM 响应:
  │   content: "已成功创建 GitHub Issue #42: 'Fix login bug'\n链接: https://github.com/user/repo/issues/42"
  │   tool_calls: []  ← 无更多工具调用
  │
  └─ TURN_END(turn=2, has_tool_calls=false)

Step 6: 完成
  ├─ 无更多 tool_calls → 退出循环
  │
  ├─ AGENT_END(total_turns=2, finish_reason="complete")
  │   └─ MemoryHooks.on_agent_end → 同步消息 + commit session
  │
  └─ 返回 AgentMessage(
       role="assistant",
       content="已成功创建 GitHub Issue #42..."
     )
```

### 阶段 5：热重载（可选）

```
如果用户修改了 skills/github/SKILL.md：

文件监听器 (watchfiles)
  ├─ 检测到 SKILL.md 变化
  ├─ 500ms 防抖
  ├─ engine.invalidate_cache()  → 清除 SkillSnapshot 缓存
  └─ 回调通知 → 下次 chat() 时自动重新加载
```

---

## 6. 与其他 Agent 哲学的对比

| 维度 | Tool First | Workflow First | **Skill First** | Conversation First |
|------|-----------|---------------|-----------------|-------------------|
| **代表** | LangChain, Semantic Kernel | LangGraph, CrewAI, n8n | **skillkit**, pi-mono | AutoGen, OpenAI Swarm |
| **核心思路** | 给大量 tools, 模型选 | 建模为 DAG/图/SOP | **极少原语 + Skill 文件扩展** | 代理间对话协作 |
| **Prompt** | 长（工具描述多） | 中（步骤描述） | **短（Skill 内容 + 缓存）** | 对话协议 |
| **Agent 自主性** | 中高（易混乱） | 低→中（受限于图） | **高（裸 ReAct loop）** | 中高 |
| **Token 效率** | 低（tool schema 大） | 中 | **高（prompt caching）** | 中 |
| **可控性** | 模型选错工具 | 强（预定义流程） | **较弱（靠模型推理）** | 可加 supervisor |
| **适用场景** | RAG + tool 混合 | 生产级/企业 | **coding agent/个人 agent** | 研究/多角色辩论 |
| **扩展方式** | 注册新 tool 函数 | 添加新 node/edge | **添加 SKILL.md 文件** | 添加新 agent |

### Skill First 的独特优势

1. **零代码扩展**：添加能力只需写一个 Markdown 文件，不需要任何代码
2. **Token 高效**：Skill 内容可缓存，避免重复传输 tool schema
3. **知识驱动**：Skill 不仅描述"能做什么"，还教会模型"怎么做"和"最佳实践"
4. **热重载**：修改 SKILL.md 即时生效，无需重启
5. **可组合**：多个 Skill 可以自然组合，模型根据上下文决定使用哪些

### Skill First 的权衡

1. **可控性较弱**：模型自行决定使用哪些 Skill 和如何组合
2. **依赖模型能力**：需要强推理能力的模型（Claude/GPT-4 级别）
3. **调试困难**：模型的决策路径不如 workflow 透明
4. **确定性低**：同样的输入可能产生不同的执行路径

---

> **总结**：SkillKit 代表了一种以"知识注入"替代"工具堆砌"的 Agent 设计哲学。它通过 Markdown 文件定义技能、最少的内置工具、事件驱动的生命周期、以及可插拔的各层组件，构建了一个极简但强大的 Agent 运行时。这种设计特别适合个人开发者 Agent 和 coding assistant 场景，在 token 效率和扩展灵活性上具有显著优势。
