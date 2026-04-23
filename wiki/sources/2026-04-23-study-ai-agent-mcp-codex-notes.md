# 来源：AI 应用体系、Agent、MCP 与 Codex 学习笔记

## 基本信息

- 标题：学习笔记：AI 应用体系、Agent、MCP 与 Codex
- 来源类型：学习笔记
- 记录日期：2026-04-23
- 原始路径：[raw/inbox/2026-04-23-study-ai-agent-mcp-codex-notes.md](../../raw/inbox/2026-04-23-study-ai-agent-mcp-codex-notes.md)

## 简要摘要

这份学习笔记试图把模型、prompt、context、tool、RAG、agent、subagent、workflow、approval、MCP、connector 和 Codex 放进同一张结构图里理解。它强调：模型负责推理，工具负责扩展能力，agent 负责规划执行，而 MCP 更像连接模型与外部工具、资源和上下文的标准接口。

## 关键点

- 持续可用的 AI 系统不只是一句 prompt，而是模型、上下文、工具和工作流共同作用的结果。
- MCP 不是模型本身，而是让模型客户端以统一协议连接外部工具和资源的接口层。
- function calling 更像应用内手工定义函数，MCP 更像把一整类外部能力按开放协议标准化接入。
- agent 的价值在于会规划、会调用工具、会继续执行多步任务，而不是只回答一轮文本。
- 真正能落地的系统还需要审批、沙箱、验证和反馈闭环，不能只看模型强弱。

## 关联页面

- [Personal Knowledge Base V1](../projects/personal-knowledge-base-v1.md)
- [LLM 上下文工程](../topics/llm-context-engineering.md)