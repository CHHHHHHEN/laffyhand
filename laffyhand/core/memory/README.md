# 反思/记忆系统设计思想

每个 Session 启动时，全量加载 Memory.md 内容注入上下文。修改 Agent 系统提示词，使其在 Agent Turn 结束之前，由 Agent 自行判断是否需要通过 memory 工具（读取 / 追加 / 更新 / 删除）直接操作 Memory.md[1][2]。

Memory.md 的控制权完全交给 Agent：
- Agent 自行决定记什么、删什么、改什么
- 去重与裁汰由 Agent 在写入时自主判断，系统不做干预
- Memory.md 设有长度上限[3]，超出时写入操作由工具（或 Agent）拒绝/截断

「Session 启动 → 加载 Memory.md → 运行中 Agent 按需操作 Memory.md」

[1] Agent 在 Turn 结束之前中自主判断是否需要记忆，系统不强制执行反思。
[2] memory 工具集包括但不限于：读取 Memory.md、追加条目、更新条目、删除条目、清空等。
[3] 长度上限为可配置参数，通过配置文件设定。

---

## System Prompt Injection

On session start, the following memory-related instructions are appended to the agent's system prompt:

```
## Memory System

You have memory tools available to preserve information across sessions.
At the **end of each task**, evaluate whether any information from this session
is worth retaining for future work. If so, use the memory tools to record it.
Record faithfully — do not fabricate, distort, or infer beyond what was actually observed or stated.

### What to Remember

Prefer information that is **stable, general, and reusable**:

- facts or patterns likely to benefit future sessions
- information not derivable from the conversation or codebase alone
- cross-cutting context that would be costly to rediscover

### What NOT to Remember

Skip information that is **transient, context-bound, or already evident**:

- content that only makes sense within the current task
- information easily re-derived from the codebase or existing artifacts
- your own reasoning steps or intermediate output
- anything already captured (check before writing)

### When Capacity Is Limited

The memory store has a configured length limit. When approaching it:

1. **Consolidate** — merge new info into existing entries instead of appending
2. **Replace** — if an entry is superseded, update it rather than adding alongside
3. **Drop** — if nothing passes the bar above, leave memory unchanged
```
