# 方法：Inbox 到 Wiki 的 Ingest

## 适用场景

当有新资料进入 `raw/inbox/`，且需要把它整理为可持续维护的知识条目时，使用这个方法。

## 步骤

1. 读取 `raw/inbox/` 中的新材料，但不修改原文件。
2. 为每份材料创建一个 `wiki/sources/` 来源页，先记录标题、类型、日期、原始路径、摘要和关键观点。
3. 判断材料中哪些内容已经足够稳定和值得复用，再提升到 `topics/`、`concepts/`、`methods/`、`decisions/`。
4. 为新建整理页补充来源区和必要回链，避免结论脱离证据。
5. 更新 `wiki/index.md`，只加入稳定入口。
6. 在 `wiki/log.md` 追加本次 ingest 记录。

## 质量检查

- 来源页是否完整记录原始路径。
- 整理页是否能回链到来源页。
- `wiki/index.md` 是否已加入稳定入口。
- `wiki/log.md` 是否已记录本次变更。
- 若来源之间存在冲突，是否明确标注，而不是直接合并。

## 相关主题

- [个人知识库维护](../topics/personal-knowledge-base-maintenance.md)

## 来源

- [来源：个人知识库 V1 周记（样本）](../sources/2026-04-22-sample-work-agent-kb-weekly-note.md)
- [来源：长周期助手的上下文工程学习笔记（样本）](../sources/2026-04-20-sample-study-context-engineering-notes.md)
- [来源：渐进式摘要法收藏摘录（样本）](../sources/2026-04-18-sample-clip-progressive-summarization.md)
