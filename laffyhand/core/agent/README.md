# agent — Agent 定义与注册

## 外部导入路径

```python
from laffyhand.core.agent import AgentInfo, AgentRegistry, get_builtin
```

## 公开 API

### `AgentInfo`

Agent 的元数据模型，所有字段：

| 字段 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `name` | `str` | — | 唯一标识 |
| `system_prompt` | `str` | — | 系统提示词 |
| `description` | `str` | `""` | 简短描述 |
| `mode` | `"primary" \| "subagent" \| "all"` | `"subagent"` | 运行模式 |
| `model` | `str \| None` | `None` | 模型别名 |
| `permission` | `dict` | `{}` | 工具权限控制 |
| `max_steps` | `int` | `50` | 最大步数 |
| `temperature` | `float \| None` | `None` | 温度参数 |
| `top_p` | `float \| None` | `None` | top_p 参数 |
| `hidden` | `bool` | `False` | 是否在列表中隐藏 |
| `options` | `dict` | `{}` | 额外配置 |

### `AgentRegistry`

Agent 注册表，负责加载和管理 Agent。

```python
registry = AgentRegistry()           # 自动加载 prompts/ 下所有 agent
registry.get("build")                # 按 name 获取 AgentInfo
registry.register(info)              # 注册自定义 agent
registry.list_subagents()            # 列出所有 subagent
registry.list_by_mode("primary")     # 按 mode 过滤
registry.list_visible()              # 列出 visible 的 agent
registry.all()                       # 返回全部副本
registry.discover(["/path/to/dir"])  # 从目录加载 .md 文件
```

### `get_builtin(name)`

直接按名称加载内置 agent 的 `AgentInfo`（无需创建 `AgentRegistry`）：

```python
info = get_builtin("compaction")
if info:
    prompt = info.system_prompt
```

---

## 配置文件格式

所有 agent 定义放置在 `prompts/` 目录下，每个 `.md` 文件包含 **YAML front-matter** + **正文**：

```markdown
---
name: my-agent
description: Custom agent
mode: subagent
permission:
  deny:
    - write
    - edit
hidden: false
---

You are 'my-agent', a custom agent.

# Instructions
Write the system prompt here.
```

- **front-matter** 字段与 `AgentInfo` 一一对应
- **正文** 作为 `system_prompt`
- 文件名 stem 用作 `name` 的 fallback（front-matter 未指定 `name` 时）
- `template_agent.md` 和 `README.md` 不会被加载
