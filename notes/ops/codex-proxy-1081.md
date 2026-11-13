---
title: Windows 上让 codex 走本地代理（127.0.0.1:1081）的完整修法
tags: [codex, proxy, windows, powershell, 排错]
owner: EYU
updated: 2026-11-13
status: verified
applies_to: codex-cli 0.168.0 / Windows 10-11 / 本地 HTTP 代理
---

# Windows 上让 codex 走本地代理（127.0.0.1:1081）的完整修法

## 一句话结论

codex 0.168 起模型请求走 WebSocket，而 WebSocket **不读 Windows 系统代理/PAC**，只认显式的
`HTTP_PROXY` / `HTTPS_PROXY`。把代理变量写进 `~/.codex/.env`，并且**杀掉旧的常驻 daemon**，问题才真正消失。

## 现象

在 PowerShell 里跑 `codex`，界面一直 `Reconnecting`，最终报连不上。日志里反复出现：

```
failed to connect to websocket: HTTP error: 403 Forbidden,
url: wss://chatgpt.com/backend-api/codex/responses
```

`~/.codex/app-server-daemon/daemon.stderr.log` 里能看到 403 页面，底部带着自己的出口 IP：

```
[IP:137.59.100.150 | Ray ID:...]   "Unable to load site ... If you are using a VPN, try turning it off."
```

那个 IP 是**国内直连出口**，说明请求根本没走代理。

## 根因（两层，第二层最坑）

1. **传输层**：0.168 的模型流量默认走 `responses_websocket`，这条通道不认系统 PAC，只认环境变量。
2. **进程层**：codex 有个常驻后端 `app-server-daemon`（`~/.codex/packages/app-server-daemon/releases/<ver>/bin/codex.exe`）。
   它**只在启动时读一次 `.env`**。如果它在配置代理之前就已经在跑，后面无论你开多少新终端、改多少次配置，
   真正发网络请求的仍然是那个旧进程。

判据：`daemon.pid` 里的 PID 启动时间早于你创建 `.env` 的时间。

## 修复步骤

### 1. 写 `~/.codex/.env`

```
HTTP_PROXY=http://127.0.0.1:1081
HTTPS_PROXY=http://127.0.0.1:1081
ALL_PROXY=http://127.0.0.1:1081
NO_PROXY=localhost,127.0.0.1,::1
```

`NO_PROXY` 要带 `localhost,127.0.0.1,::1`，否则登录回调端口和本地 MCP 服务会被一起代理掉。

### 2. 杀掉旧进程

```powershell
Get-Process codex | Stop-Process -Force
# 桌面版 Codex 也要从托盘退出，否则它会重新拉起旧 daemon
```

### 3. 新开终端重跑 `codex`

新 daemon 由这次启动的 codex 进程拉起，会继承 `.env` 里的变量。

## 验证

```powershell
# 看最新一次请求走的哪个出口
Select-String "$env:USERPROFILE\.codex\app-server-daemon\daemon.stderr.log" -Pattern 'IP:[0-9\.]+' |
    Select-Object -Last 1

# 冒烟测试：不依赖 shell 环境变量也能通
codex exec --skip-git-repo-check "Reply with exactly: PROXY-OK"
```

出口 IP 变成代理节点、`codex exec` 返回 `PROXY-OK` 即修复。

## 踩过的坑

- **端口记错**：实际是 `1081`，不是 `8081`；`8081` 上没有进程监听。
- **只在 PowerShell profile 里加函数不够**：那只影响从该终端启动的进程，管不到常驻 daemon。
- **`daemon.pid` 残留不用手删**：codex 会校验 PID 的启动时间戳，对不上就自动重建。
- **`.env` 只对 codex 生效**，不是系统级代理；想让别的工具也走，需要另外配。
- **想只在单次命令里生效**，可以在 PowerShell 里包一层函数，用 `try/finally` 注入并还原环境变量；
  但这对已经存在的 daemon 依然无效。

## 相关链接

- 上游 issue：openai/codex#29958（Windows 下 WS 不跟随系统代理）
- 上游 issue：openai/codex#14080（系统代理模式与 TUN 模式的行为差异）
