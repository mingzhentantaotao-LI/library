# 主题：LLM 上下文工程

## 主题说明

这个主题关注长周期助手如何使用有限上下文窗口，以及为什么稳定知识应外化到持久化笔记中。

## 当前稳定结论

- 上下文窗口更像有限注意力预算，而不是长期记忆仓库。
- 反复出现的稳定知识，适合沉淀到外部知识页，而不是每次重新塞进 prompt。
- 检索结果应优先返回短摘要，并保留回到来源的路径。
- 当某个工作流会重复发生时，应提炼为方法页，减少重复推导。

## 相关概念

- [上下文预算](../concepts/context-budget.md)

## 相关项目

- [Personal Knowledge Base V1](../projects/personal-knowledge-base-v1.md)

## 来源

- [来源：长周期助手的上下文工程学习笔记（样本）](../sources/2026-04-20-sample-study-context-engineering-notes.md)
