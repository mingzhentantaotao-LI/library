# 项目：Personal Knowledge Base V1

## 项目目标

建立一个面向个人长期维护的 Markdown 知识库，优先管理工作内容、学习笔记和收藏材料，并保持来源可追溯、结构可持续。

## 当前边界

- 只做 Markdown 知识库。
- 不做前端。
- 不做数据库。
- 不做复杂 RAG 平台。
- `raw/` 保存原始资料，`wiki/` 保存整理结果。

## 当前工作流

- 新材料先进入 `raw/inbox/`。
- 每次 ingest 先建立 `wiki/sources/` 来源页。
- `wiki/` 更适合作为持久化中间层：新资料进入后优先更新已有页面、补充回链和记录矛盾，而不是每次 query 从零重新拼装。
- 在更完整的 agent 工作流里，模型负责推理，外部工具和 MCP 负责连接外部世界，而 `wiki/` 承接稳定知识与结构化上下文。
- 工作材料开始进入后，project page 需要承接阶段判断、边界约束、下周计划与项目级风险，而不只是罗列结构说明。
- 只把足够稳定的内容提升到 `topics/`、`concepts/`、`methods/`、`decisions/`。
- `wiki/index.md` 保留稳定入口，`wiki/log.md` 采用追加写。

## 当前相关页面

- [个人知识库维护](../topics/personal-knowledge-base-maintenance.md)
- [Inbox 到 Wiki Ingest 方法](../methods/inbox-to-wiki-ingest.md)
- [Decision 001：V1 保持 Markdown-only](../decisions/decision-001-v1-markdown-only.md)

## 当前来源

- [来源：个人知识库 V1 周记（样本）](../sources/2026-04-22-sample-work-agent-kb-weekly-note.md)
- [来源：长周期助手的上下文工程学习笔记（样本）](../sources/2026-04-20-sample-study-context-engineering-notes.md)
- [来源：渐进式摘要法收藏摘录（样本）](../sources/2026-04-18-sample-clip-progressive-summarization.md)
- [来源：持久化中间层与持久 wiki 学习笔记](../sources/2026-04-23-study-persistent-wiki-middle-layer-notes.md)
- [来源：AI 应用体系、Agent、MCP 与 Codex 学习笔记](../sources/2026-04-23-study-ai-agent-mcp-codex-notes.md)
- [来源：个人知识库项目 V1 周复盘](../sources/2026-04-23-work-personal-knowledge-base-v1-weekly-review.md)