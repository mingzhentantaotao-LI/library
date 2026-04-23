# 主题：LLM 上下文工程

## 主题说明

这个主题关注长周期助手如何使用有限上下文窗口，以及为什么稳定知识应外化到持久化笔记中。

## 当前稳定结论

- 上下文窗口更像有限注意力预算，而不是长期记忆仓库。
- 反复出现的稳定知识，适合沉淀到外部知识页，而不是每次重新塞进 prompt。
- 持久 wiki 可以作为 LLM 的持久化中间层，减少每次 query 重新检索、拼接和总结的成本。
- 上下文不仅包括 prompt 和对话历史，也包括系统指令、文件、检索结果与工具返回。
- MCP 更适合被理解为“模型连接外部工具和资源的标准接口”，它扩展的是上下文与工具使用，而不是替代模型本身。
- 真正可落地的 agent 能力依赖工作流：规划、工具调用、结果回填、验证与审批，而不只是更强的模型。
- 对中等规模知识库，`index.md` 和 `log.md` 能在不用向量数据库的情况下提供定位线索和时间线。
- 当某个工作流会重复发生时，应提炼为方法页，减少重复推导。

## 相关概念

- [上下文预算](../concepts/context-budget.md)

## 相关项目

- [Personal Knowledge Base V1](../projects/personal-knowledge-base-v1.md)

## 来源

- [来源：长周期助手的上下文工程学习笔记（样本）](../sources/2026-04-20-sample-study-context-engineering-notes.md)
- [来源：持久化中间层与持久 wiki 学习笔记](../sources/2026-04-23-study-persistent-wiki-middle-layer-notes.md)
- [来源：AI 应用体系、Agent、MCP 与 Codex 学习笔记](../sources/2026-04-23-study-ai-agent-mcp-codex-notes.md)