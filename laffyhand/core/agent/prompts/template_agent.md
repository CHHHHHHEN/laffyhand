---
# Agent 名称（必填，需唯一）
name: my-agent

# 简短描述，用于界面展示
description: A custom agent for ...

# 运行模式：primary / subagent / all（默认 subagent）
mode: subagent

# 使用的模型别名，不填则使用主模型
model: gpt-4

# 最大执行步数（默认 50）
max_steps: 100

# 温度参数（覆盖模型默认值）
temperature: 0.7

# top_p 参数（覆盖模型默认值）
top_p: 0.9

# 是否隐藏（不在列表显示，默认 false）
hidden: false

# 工具权限控制（不填则使用全部工具）
permission:
  deny:
    - write
    - edit
    - bash

# 额外配置选项（自由格式）
options:
  flag: true
---
You are 'my-agent', a custom coding agent.

# Main instructions
Write the main system prompt here, after the front-matter.
