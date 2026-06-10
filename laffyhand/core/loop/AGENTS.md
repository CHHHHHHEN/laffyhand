# AgentTurn 时序

- 从 DB 中获取原始 Messages
- 根据 Messages 构建 Context Message
- 检查 Context Message 长度, 可选进行 Compaction
- while True:
  - If interrupt: break
  - Step++
  - 调用 LLM
  - If ToolCall:
    - 并行处理 ToolCall
  - Else:
    - break
  - 注入 Steer 消息
  - 持久化 Usage, Message
