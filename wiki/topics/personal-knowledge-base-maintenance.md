# 主题：个人知识库维护

## 主题说明

这个主题聚焦个人知识库的日常维护方式，包括来源分层、ingest 顺序、稳定入口管理和日志追加规则。

## 当前稳定结论

- `raw/` 负责保存原始资料，不应被整理逻辑回写。
- `wiki/sources/` 是 ingest 的第一层整理结果，用来建立来源、摘要和回链。
- 只有可复用的稳定信息，才应继续进入 `topics/`、`concepts/`、`methods/`、`decisions/`。
- `wiki/index.md` 应保留稳定入口，不堆积临时链接。
- `wiki/log.md` 应采用追加写，记录每次 ingest 或结构变更。
- 处理优先级应倾向未来可能被重复使用的材料。

## 关联方法

- [Inbox 到 Wiki Ingest 方法](../methods/inbox-to-wiki-ingest.md)

## 关联决策

- [Decision 001：V1 保持 Markdown-only](../decisions/decision-001-v1-markdown-only.md)

## 相关概念

- [渐进式摘要法](../concepts/progressive-summarization.md)

## 来源

- [来源：个人知识库 V1 周记（样本）](../sources/2026-04-22-sample-work-agent-kb-weekly-note.md)
- [来源：长周期助手的上下文工程学习笔记（样本）](../sources/2026-04-20-sample-study-context-engineering-notes.md)
- [来源：渐进式摘要法收藏摘录（样本）](../sources/2026-04-18-sample-clip-progressive-summarization.md)
