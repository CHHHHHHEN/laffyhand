使用 uv 管理 Python 环境
使用项目目录下的 .venv Python 环境运行脚本
使用 uv run mypy laffyhand/ 运行静态检查
使用 uv run ruff 运行风格检查
使用 uv run vulture --min-confidence 70 运行死代码检查
未经允许禁止添加新依赖

Git提交规范：
- 格式要求：type(scope): messages
- messages 需要体现出具体更改的内容，而不是笼统描述（如 resolve audit problems）