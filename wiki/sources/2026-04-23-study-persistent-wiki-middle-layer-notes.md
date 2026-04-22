# 来源：持久化中间层与持久 wiki 学习笔记

## 基本信息

- 标题：学习笔记：持久化中间层与持久 wiki
- 来源类型：学习笔记
- 日期：2026-04-23
- 原始路径：[raw/inbox/2026-04-23-study-persistent-wiki-middle-layer-notes.md](../../raw/inbox/2026-04-23-study-persistent-wiki-middle-layer-notes.md)

## 简要摘要

这份学习笔记主张把个人知识库理解为 LLM 的“持久化中间层”，而不是每次 query 都从零重新检索、拼接和总结。它把系统拆成 raw sources、wiki 和 schema 三层，并明确 ingest、query、lint、index.md、log.md、AGENTS.md、Git 和人工可读文件系统之间的协作关系。

## 关键点

- 核心不是临时回答一次问题，而是让 LLM 持续维护一套可演进的持久 wiki。
- raw sources / wiki / schema 三层分工清晰：源事实只读，结构化知识可维护，规则文件约束更新流程和回答规范。
- ingest / query / lint 是长期维护知识库的三类基本动作，不应退化成“上传 + 提问”。
- 对中等规模知识库，`index.md` 和 `log.md` 能在不用向量数据库的前提下提供目录感和时间线。
- 更稳的工作模式是 “LLM + Obsidian + Git”：文件系统可读、Git 可追溯、wiki 可持续演进。

## 关联页面

- [Personal Knowledge Base V1](../projects/personal-knowledge-base-v1.md)
- [LLM 上下文工程](../topics/llm-context-engineering.md)
