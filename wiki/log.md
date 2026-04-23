# 变更日志

## 2026-04-22

- 初始化知识库 V1 目录结构。
- 创建 `README.md`、`AGENTS.md`、`.gitignore`、`.codex/config.toml`。
- 初始化 `wiki/index.md`、`wiki/log.md`、`wiki/overview.md`。

### Ingest 001

- 按用户明确指令向 `raw/inbox/` 新增 3 份样本资料，作为首次真实 ingest 输入。
- 新建 3 个 `wiki/sources/` 来源页，分别记录工作笔记、学习笔记和收藏摘录。
- 新建 1 个项目页、2 个主题页、2 个概念页、1 个方法页、1 个决策页。
- 更新 `wiki/index.md`，补充本次 ingest 的稳定入口。
- 本次 ingest 未发现来源之间的直接冲突。

## 2026-04-23

### Ingest 002

- 向 `raw/inbox/` 新增 1 份真实学习笔记原件，主题为“持久化中间层、持久 wiki 与知识库工作模式”。
- 新建 1 个 `wiki/sources/` 来源页，记录标题、来源类型、日期、原始路径、摘要、关键点和关联页面。
- 更新 `wiki/projects/personal-knowledge-base-v1.md`，补充“wiki 作为持久化中间层”的项目级判断。
- 更新 `wiki/topics/llm-context-engineering.md`，补充持久 wiki、`index.md` 与 `log.md` 在长期上下文工程中的作用。
- 更新 `wiki/index.md`，补充本次真实材料入口。
- 本次 ingest 为最小非自动化验证，未扩展更多页面。

### Ingest 003

- 向 `raw/inbox/` 新增 1 份真实学习笔记原件，主题为“AI 应用体系、Agent、MCP 与 Codex 的关系”。
- 新建 1 个 `wiki/sources/` 来源页，记录标题、来源类型、记录日期、原始路径、摘要、关键点和关联页面。
- 更新 `wiki/projects/personal-knowledge-base-v1.md`，补充模型、工具、MCP 与持久 wiki 在 agent 工作流中的分工理解。
- 更新 `wiki/topics/llm-context-engineering.md`，补充上下文组成、MCP 角色与 agent workflow 的稳定结论。
- 更新 `wiki/index.md`，补充本次真实材料入口并把真实材料验证数更新为 2。
- 本次 ingest 继续保持最小范围，未扩展 concept / method / decision 页面。