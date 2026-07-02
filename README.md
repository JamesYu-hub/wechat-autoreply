# WeChat Auto Reply

本项目是一个本地微信自动回复实验脚本。它会定时读取微信新私聊消息，调用本地
OpenAI 兼容大模型生成中文回复，并通过 AppleScript 自动发送回微信。开启自动发送后，
模型生成的内容很可能会不经人工确认直接发给联系人，请只在充分测试并接受风险后启用。

项目默认只处理私人联系人消息，群聊、公众号、系统会话和文件传输助手等会话会被忽略。
所有运行数据都保存在本机 SQLite 数据库中；数据库、日志和本地配置默认不会上传到 GitHub。

## 功能

- 使用 `wechat-cli new-messages` 发现新会话活动。
- 使用 `wechat-cli history` 拉取游标之后的新消息。
- SQLite 去重，避免同一条消息被重复回复。
- 按联系人分组生成回复，不会把不同联系人的消息混在一起。
- 每位联系人有独立对话记忆。
- 支持一条或多条微信回复。
- 空闲时按配置间隔轮询，发现新消息后切换为 10 秒活跃轮询。
- 通过 AppleScript 搜索联系人并发送回复。
- 提供总开关、立即执行、诊断和权限测试脚本。

## 目录

```text
autoreply/                  自动回复 Python 和 shell 脚本
autoreply/config.env.example 本地配置模板
sendwechat.scpt             当前实际使用的 AppleScript 发送器
README.md                   项目说明
PRIVACY.md                  隐私说明
SECURITY.md                 安全说明
```

## 安装

需要 Python 3.11+、macOS、WeChat、`uv`，以及一个本地 OpenAI 兼容大模型服务。
当前开发和测试环境使用 Python 3.12；`pyproject.toml` 声明支持 Python 3.11+。macOS
权限弹窗里显示的 Python 版本取决于使用者本机虚拟环境。

```bash
uv venv
uv sync --extra dev
cp autoreply/config.env.example autoreply/config.env
```

`uv sync` 会按 `pyproject.toml` 中的 Git 依赖安装 `wechat-cli`。如果你想使用自己下载的
`wechat-cli`，可以在 `autoreply/config.env` 中设置：

```bash
AUTOREPLY_WECHAT_CLI=/absolute/path/to/wechat-cli
```

`wechat-cli` 需要能读取本机微信数据。它的可用性与 macOS、WeChat 版本、微信数据目录和
权限状态有关；请先阅读并验证上游项目说明：

```text
https://github.com/huohuoer/wechat-cli
```

本项目只调用 `wechat-cli new-messages`、`wechat-cli history` 和少量诊断命令，不负责保证
所有 WeChat/macOS 版本都兼容。

## 配置本地大模型

仓库不会附带 Qwen 或任何大模型文件。clone 本项目只会得到代码；模型需要使用者自己下载、
放在本机，并启动一个 OpenAI 兼容 API 服务。

基本步骤：

1. 选择一个本地模型，例如 Qwen、Llama 或其他支持本机推理的模型。
2. 将模型下载到自己的机器，例如 `/absolute/path/to/your/local/model`。
3. 用 MLX、llama.cpp、vLLM 或其他工具启动 OpenAI 兼容接口。
4. 确认服务在线：

   ```bash
   curl http://127.0.0.1:8080/v1/models
   ```

5. 在 `autoreply/config.env` 中填写：

   ```bash
   AUTOREPLY_AI_BASE_URL=http://127.0.0.1:8080/v1
   AUTOREPLY_AI_MODEL=/absolute/path/to/your/local/model
   ```

## 使用

启动自动回复：

```bash
./autoreply/control.sh start
./autoreply/install_cron.sh
```

默认空闲状态每 300 秒轮询一次；发现新私聊活动后切换为每 10 秒轮询，连续 30 次没有新活动后
恢复空闲状态。可以在 `autoreply/config.env` 中调整这些参数。

停止自动回复：

```bash
./autoreply/control.sh stop
```

查看状态：

```bash
./autoreply/control.sh status
./autoreply/diagnose.sh
```

立即抓取并生成草稿，但不发送：

```bash
./autoreply/now.sh
```

立即抓取、生成，并真实回复指定联系人：

```bash
./autoreply/now.sh --send --contact "联系人显示名或 username"
```

实时查看日志：

```bash
tail -f autoreply/logs/poll.log
```

更完整的命令说明见：

```text
autoreply/使用手册.md
```

## macOS 权限

自动发送需要 macOS Accessibility 权限。可以用下面命令触发权限请求并打开设置页：

```bash
./autoreply/request_permissions.sh
```

单独测试 AppleScript 权限，不发送消息：

```bash
./autoreply/test_applescript.sh
```

## 测试

```bash
uv run pytest
```

也可以直接运行 unittest：

```bash
./.venv/bin/python -m unittest discover -s autoreply -p 'test_*.py'
```

## 隐私

不要上传真实运行数据。`.gitignore` 已默认忽略：

```text
autoreply/config.env
autoreply/logs/
autoreply/*.sqlite3
autoreply/scheduler_state.json
.env
.venv/
data/
vendor/wechat-cli/
```

如果准备公开仓库，请先阅读 `PRIVACY.md` 和 `SECURITY.md`。
