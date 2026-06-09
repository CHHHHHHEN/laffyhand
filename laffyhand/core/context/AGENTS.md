# 上下文管理设计

引入一个上下文管理器：先尝试轻量的消息修剪，当接近上下文窗口限制（80%）或者用户手动触发压缩机制（调用 LLM 将早期对话压成摘要并分裂出子会话）。

修剪是同步操作，仅替换大型工具结果的内容，不创建新会话。链式压缩是异步操作，涉及 LLM 调用和会话分裂，新旧会话通过父子关系形成压缩链。轮次结束后若发生压缩，可选择自动注入一条"继续"消息让模型继续运行。

早期对话选取策略：保留最近N轮完整消息，从倒数N+1轮开始向前选择。

消息修剪：当工具调用结果位于40K近期上下文范围之外时，进行修剪替换。修剪后仍保留工具调用的参数等信息，让Agent知道自己曾经读取过这个文件。

从 DB 获取 Session 所有 Message（分页，逆序）
Compaction 重排
- 找到 compaction-user 和对应的 summary assistant
- 将 compaction-user + summary 移到消息列表前面
- 将 compaction 保留的 tail 消息插入中间
- 最终顺序: compaction-user, summary, 保留的tail..., 最新消息
提取本轮关键信息
- 最新的 user message
- 最新的 assistant message
- 最新的已结束 assistant message（带 finish reason）
- 待处理任务（从 finished 之后的消息中提取 compaction / subtask）
如果有待处理任务, 处理完后重新开始, 不走后续步骤
注入 Reminders
- 检查 agent 切换（plan → build）, 追加对应提示文本到最新 user message
- 检查 plan mode, 追加 plan 文件路径提示
Steer 包裹（仅在 step > 1 时）
- 对 finished 之后所有 user message 中非合成的 text part
- 用 <system-reminder> 包裹, 提示 LLM 用户发了新消息请处理
并行构建四个部分:
- 环境信息: 模型名, 工作目录, git, 平台, 日期
- 指令: 全局 AGENTS.md + 项目根 AGENTS.md
- Skills: 当前 agent 可用的 skill 列表
- user: text / compaction→"What did we do?" / subtask→"executed by user"
- assistant: text, reasoning, step-start, tool-call, tool-result（按原始顺序排列）
拼装最终输入
- system = 环境, 指令, skills
- messages = 模型消息...,
传给 LLM
