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

### Review 001

- 补充 V1 reviews 规则，明确 review 的触发时机、最小检查清单、输出形式与回写原则。
- 新建 `wiki/reviews/review-template.md`，作为手动 review 的最小模板。
- 更新 `wiki/index.md`，补充 review 模板入口。
- 本次仅设计规则，不实现脚本或自动任务。

### Templates 001

- 在 `raw/templates/` 下新增工作周记、项目复盘、需求方案草稿 3 份材料捕获模板。
- 在 `AGENTS.md` 中补充 `raw/templates/` 的目录职责，并说明 review 默认从 `wiki/reviews/review-template.md` 起步。
- 在 `README.md` 中补充 `raw/templates/` 的最小使用说明。
- 本次仅补模板与规则说明，不实现自动化或新增系统功能。

### Ingest 004

- 向 `raw/inbox/` 新增 1 份真实工作复盘原件，主题为“personal-knowledge-base-v1 本周阶段判断、风险与下周计划”。
- 新建 1 个 `wiki/sources/` 来源页，记录标题、来源类型、日期、原始路径、摘要、关键点和关联页面。
- 更新 `wiki/projects/personal-knowledge-base-v1.md`，补充 project page 在承接项目级判断、风险与下周计划上的作用。
- 更新 `wiki/topics/personal-knowledge-base-maintenance.md`，补充跨主题工作材料优先挂靠维护主题的理由，而不是分散写入多个已有页。
- 更新 `wiki/index.md`，补充本次工作材料入口并把真实材料验证数更新为 3。
- 本次 ingest 继续保持最小范围，未扩展 method / decision / concept 页面。

## Handoff 001 - 2026-04-28

- 动作类型：上下文整合
- 新增页面：`PROJECT_HANDOFF.md`
- 更新页面：`README.md`、`AGENTS.md`
- 说明：为新会话或新 project 提供压缩交接上下文；正式维护规则仍以 `AGENTS.md` 为准。
