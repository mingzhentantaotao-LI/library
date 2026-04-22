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
