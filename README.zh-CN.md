# TermPilot

[English](README.md) | [简体中文](README.zh-CN.md)

TermPilot 让 ChatGPT 能够以结构化方式查看和操作 Mac 上已经打开的 iTerm2 会话。它主要面向 ChatGPT Classic 与 macOS Work with Apps 的组合使用场景：Work with Apps 提供终端上下文，TermPilot 则通过四个 MCP 工具补上会话发现、受限终端读取以及显式命令执行能力。

## 前置条件

- macOS，并已运行 iTerm2。
- Python 3.13 和 [uv](https://docs.astral.sh/uv/)。
- 已启用 iTerm2 Python API。参见 [iTerm2 Python API 文档](https://iterm2.com/python-api/)。
- 在需要使用 `run_command` 的 shell 中安装 iTerm2 [Shell Integration](https://iterm2.com/documentation-shell-integration.html)。TermPilot 依赖 Shell Integration 提供的 prompt 状态和命令完成元数据来安全执行命令。

## 安装与运行

使用 `uv` 从 PyPI 安装：

```bash
uv tool install termpilot-plugin
termpilot
```

也可以不安装，直接运行：

```bash
uvx --from termpilot-plugin termpilot
```

从仓库进行开发时，在仓库根目录执行：

```bash
uv sync
uv run termpilot
```

`termpilot` 通过 stdio 提供 MCP 服务。stdout 专门用于 MCP 消息，诊断日志输出到 stderr。本地 MCP 客户端可以直接运行 PyPI 包：

```json
{
  "mcpServers": {
    "termpilot": {
      "command": "uvx",
      "args": [
        "--from",
        "termpilot-plugin",
        "termpilot"
      ]
    }
  }
}
```

## 工具

| 工具 | 用途 | 权限 |
| --- | --- | --- |
| `list_sessions` | 列出可访问的 iTerm2 会话，以及 ID、标签、主机、用户、cwd、当前会话标记和就绪状态 | 只读 |
| `get_current_session` | 获取当前聚焦的 iTerm2 会话 | 只读 |
| `read_terminal` | 根据精确的 `session_id` 读取有边界限制的终端可见内容 | 只读 |
| `run_command` | 向精确的 `session_id` 对应会话发送用户明确提供的命令，并可选择等待执行完成 | 写入 |

常规使用流程：

1. 调用 `get_current_session` 或 `list_sessions` 获取目标会话。
2. 需要查看终端内容时，将返回的精确 `session_id` 传给 `read_terminal`。
3. 只有在用户明确要求执行某条命令时，才调用 `run_command`。
4. 根据返回的 session ID、命令、状态、退出码和受限输出分析执行结果。

## 安全行为

- `run_command` 必须提供精确的 `session_id`；不会使用标题或模糊匹配结果作为写入目标。
- 如果目标会话缺失、已关闭、不可访问或存在歧义，操作会直接失败，不会自动改投其他会话。
- 终端内容、命令历史、标题和之前的工具输出都只作为观察数据，不会被自动转换成待执行命令。
- 命令会发送到已有 iTerm2 会话，并在 API 支持时关闭 broadcast input。TermPilot 不会新建 shell、窗口或 SSH 连接。
- 执行命令前必须确认会话处于正常 shell prompt。正在执行命令或运行交互程序的会话会被拒绝写入。
- 超时只表示 TermPilot 停止等待结果，并不表示底层 shell 命令已被取消。

## 验证

运行自动化检查：

```bash
uv run pytest
uv run ruff check src tests
uv run ruff format --check src tests
```

live 测试默认不会运行；它只检查当前运行中的 iTerm2 实例会话列表：

```bash
TERMPILOT_LIVE_ITERM2=1 uv run pytest tests/integration/test_iterm2_live.py -q
```

完整的手动“查看 → 操作 → 再查看”流程见 [`specs/001-chatgpt-terminal-actions/quickstart.md`](specs/001-chatgpt-terminal-actions/quickstart.md)。

## 连接 ChatGPT

ChatGPT 不能直接启动本地 stdio 进程。TermPilot 现在可以通过 [OpenAI Secure MCP Tunnel](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels)，使用官方 `tunnel-client` 的 managed runtime，把同一个本地 MCP 服务接到 ChatGPT。

### 1. 安装 `tunnel-client`

macOS + Homebrew：

```bash
brew install openai/tools/tunnel-client
tunnel-client --version
```

TermPilot 不会内置或锁定 `tunnel-client` 版本，而是直接使用 `PATH` 中的
`tunnel-client`。

### 2. 创建 Tunnel 和 Runtime API Key

`tunnel-client help quickstart` 给出的官方入口是：

- [Tunnels 管理](https://platform.openai.com/settings/organization/tunnels)：创建
  tunnel，并保存返回的 `tunnel_...` ID。
- [Runtime API Keys](https://platform.openai.com/settings/organization/api-keys)：
  创建给长期运行的 tunnel runtime 使用的 key。创建/使用这个 key 的主体需要
  对目标 tunnel 拥有 **Tunnels Read + Use** 权限。
- [Admin API Keys](https://platform.openai.com/settings/organization/admin-keys)
  只用于通过 `tunnel-client admin ...` 创建、修改、删除 tunnel；不要把 admin
  key 当成长期开启 runtime 的 key。

如果希望完全通过 CLI 创建 tunnel，可以先配置 admin key，再使用
`tunnel-client` 自带的 tunnel 管理命令。创建时至少需要一个 organization 或
workspace scope：

```bash
export OPENAI_ADMIN_KEY="sk-admin-..."
tunnel-client admin tunnels create \
  --name "termpilot" \
  --description "TermPilot local iTerm2 MCP" \
  --organization-id org_...
```

也可以使用 `--workspace-id ws_...`，或者同时指定 organization 与 workspace。
保存返回的 `tunnel_...` ID。Tunnel 创建完成以后，TermPilot runtime 只需要这个
ID 和 runtime API key，不再需要 admin key。

### 3. 保存并加载 Runtime API Key

推荐在仓库根目录创建 `.env`：

```dotenv
CONTROL_PLANE_API_KEY=sk-...
```

本仓库已经忽略 `.env`，但 **TermPilot 和 tunnel-client 都不会自动读取
`.env`**。每次启动、查看状态或诊断前，要先把它加载进当前 shell：

```bash
set -a
source .env
set +a
```

也可以直接 export：

```bash
export CONTROL_PLANE_API_KEY="sk-..."
```

TermPilot 写入 tunnel-client profile 的只是
`env:CONTROL_PLANE_API_KEY` 引用，不会把真实 key 放进命令行，也不会打印它。

### 4. 启动 managed runtime

连接已有 tunnel：

```bash
uv run termpilot chatgpt setup --tunnel-id tunnel_0123456789abcdef0123456789abcdef
```

`setup` 会启动一个长期运行的 `tunnel-client` managed runtime，并由它启动当前
仓库中的 `python -m termpilot.main` stdio MCP 服务。正常情况下会看到：

```text
Process running: yes
Healthy: yes
Ready: yes
```

查看状态或诊断：

```bash
uv run termpilot chatgpt status
uv run termpilot chatgpt doctor
```

Mac 重启、或者执行过 `disconnect` 后，再次 `source .env` 并执行同一条
`setup --tunnel-id ...` 即可；会复用已有 tunnel。

只停止本地 runtime、保留 OpenAI 侧 tunnel：

```bash
uv run termpilot chatgpt disconnect
```

### 5. 在 ChatGPT Classic 里添加 TermPilot

`setup` 成功后：

1. 打开 **ChatGPT 设置 → 插件**（也可以直接打开
   [ChatGPT Plugins](https://chatgpt.com/plugins)）。
2. 创建新的 developer-mode 插件/app，例如命名为 `termpilot`。
3. **连接**选择 **Tunnel**，不要选择 **服务器 URL**。
4. 选择刚才创建的 tunnel，或者粘贴 `tunnel_id`。
5. 保存插件，并按需要允许 TermPilot 的工具权限。

ChatGPT 发现和调用 MCP 工具时，Mac 上的 tunnel runtime 必须保持运行。使用
Secure MCP Tunnel 连接本地 TermPilot 时，不需要给 TermPilot MCP 再配置 OAuth。

## Frequently Asked Questions / 常见问题

- `tunnel-client is not installed or is not available on PATH`
- 已经把 `CONTROL_PLANE_API_KEY` 写进 `.env`，为什么仍然提示 missing？
- `CONTROL_PLANE_API_KEY` 和 `OPENAI_ADMIN_KEY` 有什么区别？
- 为什么手工执行 `tunnel-client runtimes connect` 会提示缺少 key？
- ChatGPT 能把请求转发过来，但 TermPilot 报 `iTerm2 is not running or its Python API is disabled`
- 为什么旧版 TermPilot 在直接 iTerm2 测试成功时仍会失败？
- tunnel 日志已经出现 `dispatcher forwarded command to MCP server`，为什么 ChatGPT 仍得到 iTerm2 错误？
- ChatGPT 新插件里同时有“服务器 URL”和“隧道”，应该选哪个？
- tunnel-client 日志里出现 `Codex detected without Tunnel MCP plugin` 有影响吗？
- 怎么快速判断故障在哪一层？


### `tunnel-client is not installed or is not available on PATH`

安装并确认命令可见：

```bash
brew install openai/tools/tunnel-client
which tunnel-client
tunnel-client --version
```

### 已经把 `CONTROL_PLANE_API_KEY` 写进 `.env`，为什么仍然提示 missing？

`.env` 文件本身不会自动 export 环境变量。启动或诊断 tunnel runtime 的每个
shell/process 都要先加载：

```bash
set -a
source .env
set +a
uv run termpilot chatgpt setup --tunnel-id tunnel_...
```

### `CONTROL_PLANE_API_KEY` 和 `OPENAI_ADMIN_KEY` 有什么区别？

`CONTROL_PLANE_API_KEY` 是长期运行的 tunnel daemon 使用的 runtime key，需要
**Tunnels Read + Use**。`OPENAI_ADMIN_KEY` 用于
`tunnel-client admin tunnels create` 等 tunnel 管理操作。连接已经存在的 tunnel
时，TermPilot runtime 不需要 admin key。

### 为什么手工执行 `tunnel-client runtimes connect` 会提示缺少 key？

生成的 profile 保存的是 `env:CONTROL_PLANE_API_KEY` 这种环境变量引用。因此启动
profile 的进程必须真的拥有这个环境变量。推荐直接使用
`uv run termpilot chatgpt setup ...`，它会统一生成正确的 runtime-key 引用和 MCP
启动命令。

### ChatGPT 能把请求转发过来，但 TermPilot 报 `iTerm2 is not running or its Python API is disabled`

先检查 iTerm2：

1. 打开 **iTerm2 → Settings → General → Magic**。
2. 勾选 **Enable Python API**。
3. 选择 **Allow all apps to connect**，或者明确允许运行 TermPilot 的进程连接。

然后从 TermPilot 的 Python 环境直接验证 iTerm2 API：

```bash
uv run python - <<'PY'
import asyncio
import iterm2

async def main():
    connection = await iterm2.Connection.async_create()
    app = await iterm2.async_get_app(connection)
    print([s.session_id for w in app.windows for t in w.tabs for s in t.sessions])

asyncio.run(main())
PY
```

如果能打印 session ID，说明 iTerm2 Python API 本身正常，应该继续排查本机
TermPilot → iTerm2 这一段，而不是重新创建 ChatGPT tunnel。

### 为什么旧版 TermPilot 在直接 iTerm2 测试成功时仍会失败？

早期 adapter 调用了
`iterm2.async_get_app(..., create_if_needed=False)`。在 iTerm2 3.6.x 上，即使
iTerm2 已经运行，这个调用也可能返回 `None`。现在 TermPilot 会允许 SDK 创建
`App` wrapper，与能够正常工作的 `iterm2.async_get_app(connection)` 行为一致。

### tunnel 日志已经出现 `dispatcher forwarded command to MCP server`，为什么 ChatGPT 仍得到 iTerm2 错误？

这条日志已经证明 **ChatGPT → Secure MCP Tunnel → TermPilot MCP** 是通的。下一步
应检查本机 **TermPilot → iTerm2 Python API**，不要继续反复重建 ChatGPT 插件或
tunnel。

### ChatGPT 新插件里同时有“服务器 URL”和“隧道”，应该选哪个？

选择 **隧道 / Tunnel**，然后选择或粘贴 `tunnel_id`。**服务器 URL** 是给网络上
可直接访问的 HTTP/SSE MCP server 使用的，不是这里的 TermPilot 方案。

### tunnel-client 日志里出现 `Codex detected without Tunnel MCP plugin` 有影响吗？

没有。这条提示针对可选的 Codex tunnel plugin 集成，不会阻止 ChatGPT Classic
通过 developer-mode 插件使用 TermPilot tunnel。

### 怎么快速判断故障在哪一层？

按下面顺序检查：

1. `uv run termpilot chatgpt status`：runtime 应处于 running / healthy / ready。
2. tunnel 日志出现 `dispatcher forwarded command to MCP server`：说明 ChatGPT 到
   TermPilot 的 tunnel 链路正常。
3. 执行上面的 iTerm2 Python 直连脚本：确认本机 iTerm2 API 正常。
4. 最后回到 ChatGPT 的 TermPilot 插件调用 `list_sessions`。
