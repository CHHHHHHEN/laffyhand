# LaffyHand 开发指南

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.14, aiohttp 3.13, pydantic 2.13, httpx 0.28, loguru 0.7, MCP ≥1.26, PyYAML 6.0 |
| 前端 | TypeScript 5.8, React 19, React Router DOM 7, Zustand 5, TanStack React Query 5, Tailwind CSS 4, Vite 8, Vitest 4 |
| 工具 | uv, pnpm, mypy 2.1, ruff 0.15, vulture 2.16 |

## 核心原则

- 使用 `uv` 管理 Python 环境，脚本通过项目目录下的 `.venv` 运行
- **未经允许禁止添加新依赖**
- **允许破坏性重构**，优先保证架构正确性及可维护性，而非兼容性
- **任何代码修改**（包括 fix / feature / refactor / UI 重构 / 样式变更）**必须**编写对应测试覆盖改动，不允许以"纯 UI 无逻辑变更"为由跳过测试

## 开发命令

### 后端（修改后依次执行）

```bash
uv run mypy laffyhand/          # 静态类型检查
uv run ruff                     # 代码风格检查
uv run vulture --min-confidence 70  # 死代码检测
uv run pytest tests/            # 运行测试
```

### 前端 UI（修改后依次执行）

```bash
pnpm build                      # 构建
pnpm eslint                     # 代码风格检查
pnpm vitest run                 # 运行测试
```

## 问题排查规范

1. 优先选择 **客观最佳方案**，而非 quick fix
2. 遇到问题先问 **WHY**，搜索根因（**ROOT CAUSE**），而非盲目求解
3. 无法确认根因时，优先添加 **DEBUG 日志**，而非猜测式修复

## Git 提交规范

- **格式**: `type(scope): messages`
- `messages` 需体现具体更改内容（如 `feat(auth): add OAuth2 login`），**禁止**笼统描述（如 `resolve audit problems`）
- `scope` 需具体到模块，**禁止**宏大概括（如 `audit`）
- 每个 commit 保持**单一主题**（单 fix / 单 feature / 单主题），否则拆分为多个 commit
