LLM 在当前 Agent Turn 中正常推理
LLM 决定调用 task tool
从当前 agent 列表中找到目标 agent
检查权限（用户是否允许调用 task tool）
创建一个新的子 session，关联当前 session 作为 parent
子 session 的权限继承父 session，同时合并目标 agent 的规则
获取当前 assistant message 的信息来确定使用哪个模型
在子 session 中调用 prompt，传入 task tool 的参数中的 prompt 文本
子 session 以目标 agent 的身份运行完整的 agent loop
子 session 跑完后返回最后一条 assistant 消息的文本内容
将结果包装成结构化格式
记录 tool 调用信息（工具名、参数、状态设为 running）
