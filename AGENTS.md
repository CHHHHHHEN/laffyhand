使用 uv 管理 Python 环境
使用项目目录下的 .venv Python 环境运行脚本
未经允许禁止添加新依赖
允许破坏性重构，优先保证架构正确性以及可维护性，而不是考虑兼容性

假如修改了后端:
- 使用 uv run mypy laffyhand/ 运行静态检查
- 使用 uv run ruff 运行风格检查
- 使用 uv run vulture --min-confidence 70 运行死代码检查

假如修改了前端 UI:
- 使用 pnpm build 进行构建测试
- 使用 eslint 检查代码风格

问题排查规范：
- 优先选择**客观**最佳方案，而不是 Quick fix
- 遇到问题先问 WHY，搜索根因（ROOT CAUSE），而不是 JUST SOLVE PROBLEM

Git提交规范：
- 格式要求：type(scope): messages
- messages 需要体现出具体更改的内容, 而不是笼统描述(如 resolve audit problems)
- score 需要具体到模块, 禁止宏大概括(e.g. audit)
- 确保 commit 内容为单个fix/单个feature/单一主题, 如果不是则需要 spilt 为多个 commit