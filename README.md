# 个人知识库 V1

这是一个面向个人长期维护的 Markdown 知识库，目标是把工作内容、学习笔记和收藏材料放到一个可追溯、可持续整理的仓库里。

V1 只做两层：

- `raw/`: 原始资料层，保存原件，只读。
- `wiki/`: 整理后的知识层，负责索引、摘要、结论和回链。

不做的事情：

- 不做前端
- 不做数据库
- 不做复杂 RAG 平台

## 目录结构

```text
personal-knowledge-base/
├── AGENTS.md
├── README.md
├── .gitignore
├── .codex/
│   └── config.toml
├── raw/
│   ├── inbox/
│   ├── work/
│   ├── study/
│   ├── clips/
│   └── assets/
├── wiki/
│   ├── index.md
│   ├── log.md
│   ├── overview.md
│   ├── projects/
│   ├── topics/
│   ├── concepts/
│   ├── methods/
│   ├── decisions/
│   ├── sources/
│   └── reviews/
└── scripts/
    ├── ingest/
    ├── lint/
    ├── export/
    └── utils/
```

## 新材料怎么放进来

以后所有新材料都先进入 `raw/inbox/`。

建议做法：

1. 直接把原文件放进 `raw/inbox/`。
2. 不要在导入前先改写原文或覆盖原件。
3. 文件名尽量保留来源语义，例如日期、主题、来源名。

示例：

- `raw/inbox/2026-04-22-ai-agent-notes.md`
- `raw/inbox/2026-04-22-product-review.pdf`
- `raw/inbox/2026-04-22-bookmark-llm-context-window.html`

## 我会如何处理这些材料

作为这个仓库的维护者，我会按以下方式工作：

1. 读取 `raw/inbox/` 中的新材料，但不修改原文件。
2. 在 `wiki/sources/` 建立来源页，登记路径、来源、主题和摘要。
3. 把值得沉淀的内容整理到 `wiki/projects/`、`wiki/topics/`、`wiki/concepts/`、`wiki/methods/`、`wiki/decisions/` 或 `wiki/reviews/`。
4. 更新 `wiki/index.md`，让新知识能被导航到。
5. 在 `wiki/log.md` 追加本次处理记录。

## V1 边界

这个版本只服务于稳定、低维护成本的个人知识整理：

- 以 Markdown 为主
- 以目录结构和链接关系为主
- 以人工可读、可追溯为主

V1 明确不包含：

- 网站或前端界面
- 数据库存储
- 向量库、检索服务、工作流编排平台等复杂 RAG 基础设施

如果未来要扩展，也应先保证当前这套 `raw/ + wiki/` 结构仍然成立。
