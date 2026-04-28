# Project Handoff

这份文件是给新会话、新 project 或接手维护者的压缩上下文。它不是规则源头；长期规则仍以 `AGENTS.md` 为准。

## 当前目标

这个仓库是一个 Markdown-only 的个人知识库 V1，用来长期沉淀工作内容、学习笔记和收藏材料。

V1 的核心不是复杂系统，而是稳定的两层结构：

- `raw/`: 原始资料层，只读，保存证据和回溯材料。
- `wiki/`: 整理后的知识层，保存索引、摘要、结论、回链和复盘。

## 当前完成度

已经完成：

- V1 目录骨架和项目说明。
- Git 初始化和首个基线提交。
- 样本 ingest。
- 多轮真实 ingest，其中已经包含学习材料和工作复盘材料。
- 最小 lint 脚本：`scripts/lint/check_kb.py`。
- `wiki/sources/` 最小模板规范。
- `raw/inbox/` 与 `wiki/sources/` 命名映射规则。
- 单轮 ingest 页面上限规则。
- V1 reviews 规则设计和 `wiki/reviews/review-template.md`。
- 工作材料捕获模板：`raw/templates/`。

## 新会话启动顺序

新会话接手时，建议按这个顺序读取：

1. `PROJECT_HANDOFF.md`: 先建立当前阶段上下文。
2. `AGENTS.md`: 读取正式维护规则和边界。
3. `README.md`: 理解给人看的项目说明和使用方式。
4. `wiki/index.md`: 查看当前已有知识入口。
5. `wiki/log.md`: 查看最近发生过什么。

接手后先运行：

```bash
git status --short --branch
python3 scripts/lint/check_kb.py
```

## 当前工作方式

### Ingest

每轮 ingest 必须小步处理：

- 不修改 `raw/` 中原始文件。
- 先为 `raw/inbox/` 中的材料创建对应 `wiki/sources/` 页面。
- 来源页文件名默认与原始文件同 basename，只把扩展名改成 `.md`。
- 来源页之外，最多更新 1 个 project page 和 1 个其他知识页。
- 同步更新 `wiki/index.md` 和 `wiki/log.md`。
- 跑 lint，确认工作树干净，再提交。

### Review

reviews 目前只做规则和记录，不做自动化：

- 每周、每 2 次真实 ingest 后、或出现结构漂移迹象时触发。
- 检查 source 是否未被有效提升或关联、project/topic 是否长期未更新、跨主题材料是否放错位置、命名和索引是否漂移。
- 输出到 `wiki/reviews/YYYY-MM-DD-review-<scope>.md`。
- review 先记录发现和建议动作；是否回写其他 wiki 页面，应另起一轮小改动判断。

### 捕获真实材料

如果暂时缺少真实工作材料，不要硬做 ingest。优先使用 `raw/templates/` 下的模板生成更稳定的输入：

- `raw/templates/work-weekly-note-template.md`
- `raw/templates/project-retrospective-template.md`
- `raw/templates/requirements-solution-draft-template.md`

填好的材料再放入 `raw/inbox/`，之后按 ingest 规则处理。

## 当前边界

V1 阶段继续保持克制：

- 不做前端。
- 不做数据库。
- 不做复杂 RAG。
- 不做 ingest 自动化。
- 不做 review 自动化。
- 不把临时讨论直接写成稳定知识。

除非用户明确改变方向，否则优先继续验证 `raw/ + wiki/` 这套结构是否可持续。

## 下一步判断

当前最适合的下一步取决于是否有真实材料：

- 如果有新的真实工作材料：做一轮最小非自动化 ingest。
- 如果没有真实材料：先用 `raw/templates/` 捕获工作周记、项目复盘或需求/方案草稿。
- 如果再积累 1-2 轮真实工作材料：再考虑是否做轻量工具化增强，例如更顺手的 lint 入口或 checklist。

不要因为规则已经成形就急着扩功能；这个项目目前最有价值的部分，是把材料、规则、索引、日志和复盘保持在可持续的小步循环里。
