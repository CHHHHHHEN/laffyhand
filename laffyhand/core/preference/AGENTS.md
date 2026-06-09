系统启动时:
  - 加载项目根: <worktree>/AGENTS.md
    - 注入 system prompt

中途加载 (Read tool 执行时):
  Agent 调用 Read
    - 获取已经加载过的 AGENTS.md 路径集合
    - 从当前文件夹路径向上遍历, 直到 workspace root 停止
      - 查找文件夹下是否存在 AGENTS.md
      - If AGENTS.md 已经加载
        - continue
      - Else
        - 将该 AGENTS.md 路径加入 result
    - If results
      - 后续在工具调用结果中附上新增 AGENTS.md 内容

新的 AGENTS.md 内容需要处于 <system-reminder> 标签内部
