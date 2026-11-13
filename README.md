# 团队知识库

一个**纯文本、可版本化、可整包迁移**的知识库。笔记是 Markdown，检索器是一个零依赖的 Python 脚本，
既能在命令行里自己查，也能通过 MCP 接进 codex / claude code / DSH 等 agent。

## 目录结构

```
knowledge-base/
├─ notes/                 # 唯一需要人维护的内容
│  ├─ ops/                # 运维排错
│  ├─ concept/            # 概念与原理
│  └─ tools/              # 工具用法
├─ tools/kb.py            # 建索引 / 检索 / MCP server（只用 Python 标准库）
├─ .kb/                   # 本地索引，自动生成，已 gitignore
├─ README.md
└─ .gitignore
```

三层职责，别混：

1. **数据层** `notes/`：Markdown 纯文本，Obsidian 可以直接打开这个目录当 vault。
2. **索引层** `.kb/index.json`：切块 + 词频，随时重建，不进版本库。
3. **接口层** `tools/kb.py`：`search` 给人用，`mcp` 给 agent 用。

## 快速开始

前置：Python 3.8+（无第三方依赖）。

```powershell
# 建/重建索引
python tools\kb.py index notes

# 命令行检索
python tools\kb.py search "codex 一直重连怎么修" -k 5

# 作为 MCP server 给 agent 用
python tools\kb.py mcp
```

`.kb/index.json` 的生成与查询都**不联网**，内网可用。

MCP 模式会自动检测索引文件变化：新建/修改笔记后只要执行一次 `index`，**正在运行的 agent 会话无需重启**即可检索到新内容。

## 新增一条知识

在 `notes/` 对应分类下新建 `<英文短名>.md`，开头加 frontmatter：

```markdown
---
title: 一句话标题
tags: [codex, proxy]
owner: 你的名字
updated: 2026-11-13
status: draft | verified
---
```

正文建议按「现象 → 根因 → 解决 → 验证 → 踩过的坑」来写，方便别人复用。
写完执行一次 `python tools\kb.py index notes` 让新内容可被检索到。

## 接进 agent

```powershell
# codex
codex mcp add local-kb -- python <本目录>\tools\kb.py mcp
# claude code
claude mcp add local-kb -- python <本目录>\tools\kb.py mcp
```

DSH 走同样的 MCP（stdio）配置。

## 团队协作与上云

- 用 Git 管理：`git clone` 一份就能参与，改动走 PR/评审。
- 索引文件不进库，各自本地重建，避免合并冲突。
- 云端：推到 GitHub / Gitee / 公司 GitLab 的私有仓库即可。
- 整包带走：`Compress-Archive` 打成 zip，或 `git bundle` 带上完整历史。

## 内网使用

`tools/kb.py` 只用标准库，内网机器有 Python 就能跑；
没有 Python 时可以把 Python 运行时和本目录一起打包带进去，解压即用。
