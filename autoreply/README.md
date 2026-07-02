# WeChat Private Auto-Reply Collector

完整中文命令、参数和文件说明请查看：

```text
autoreply/使用手册.md
```

第一阶段使用 `wechat-cli new-messages` 发现发生变化的会话，再调用 `wechat-cli history`
拉取该联系人游标之后的全部私聊文本并写入 `unread_messages.sqlite3`。群聊、公众号、
公众号聚合入口、系统会话和本人发出的消息都会被忽略。

调度器的空闲抓取间隔由 `config.env` 的 `AUTOREPLY_IDLE_INTERVAL_SECONDS` 决定，默认是
300 秒。发现新的个人私聊后，切换为每 10 秒抓取一次；连续 30 个 10 秒轮询均无新消息后
恢复为空闲间隔。

可通过 `config.env` 的 `AUTOREPLY_IDLE_INTERVAL_SECONDS` 临时调整空闲间隔。小于 60 秒时，
调度进程会保持运行并自行按该间隔轮询，不受标准 cron 最小一分钟粒度限制。

## 文件

- `poll_unread.py`: 使用 `new-messages` 发现会话、使用 `history` 拉取全部新文本
- `adaptive_scheduler.py`: 保存并执行空闲间隔/10 秒活跃间隔的自适应调度状态
- `unread_messages.sqlite3`: 未读私聊消息队列，使用唯一指纹去重
- `run_poll.sh`: cron 入口，带并发锁和日志
- `install_cron.sh`: 安装每分钟唤醒一次的 cron；是否实际抓取由调度变量决定
- `scheduler_state.json`: 当前时间间隔和连续空轮询次数
- `generate_replies.py`: 按联系人聚合全部 `pending` 消息并调用本地 Qwen 生成回复草稿

数据库还包含：

- `session_audit`: 最近会话分类，以及每个会话被允许或忽略的原因
- `contact_cursors`: 私聊会话历史拉取游标
- `reply_drafts`: 每个联系人的 Qwen 回复草稿与完整 Prompt
- `reply_draft_messages`: 回复草稿与原始未读消息的关联
- `logs/poll.log`: 运行日志

## 手动运行

```bash
./autoreply/run_poll.sh
sqlite3 autoreply/unread_messages.sqlite3 \
  "SELECT contact_name, message_text, status FROM unread_messages ORDER BY id DESC;"
```

立即忽略空闲等待，抓取消息并生成草稿：

```bash
./autoreply/now.sh
```

立即抓取、生成，并真实回复指定联系人：

```bash
./autoreply/now.sh --send --contact "联系人显示名或 username"
```

立即命令仍尊重总开关，并与 cron 共用运行锁。Qwen 服务需要保持运行；真实发送必须同时提供
`--send` 和 `--contact`，避免意外批量发送。立即命令成功结束后会重新开始空闲计时。

## 总开关

```bash
./autoreply/control.sh start
./autoreply/control.sh stop
./autoreply/control.sh status
```

`stop` 后 cron 任务仍保留，但会立即退出，不读取微信、不调用 Qwen，也不发送消息。
删除 cron 可运行：

```bash
crontab -l | grep -v '# summaryassist-autoreply-poll' | crontab -
```

## 后台发送权限

实际发送路径是：

```text
Python -> /usr/bin/osascript -> sendwechat.scpt -> System Events -> WeChat
```

没有辅助功能权限时，消息仍会被抓取并生成草稿，但发送会报
`not allowed to send keystrokes (1002)`。

从 Terminal 触发权限请求并打开相关设置页：

```bash
./autoreply/request_permissions.sh
```

Terminal 只能触发请求或打开设置页，不能直接批准权限。最终的允许开关必须由用户手动确认。
`Automation` 页面没有 `+` 按钮是 macOS 的正常设计；条目只会在应用实际发送 Apple Event
后出现。本项目不要求 `Python -> WeChat` 的 Automation 条目：

- Python/wechat-cli 负责读取微信数据，需要“其他 App 数据”或“完全磁盘访问”权限。
- Python 启动的 `/usr/bin/osascript` 负责模拟键盘发送，需要“辅助功能”权限。

一键检查运行状态：

```bash
./autoreply/diagnose.sh
```

按联系人生成回复草稿：

```bash
./.venv/bin/python -m autoreply.generate_replies
```

预览等待发送的最新草稿，不会实际发送：

```bash
./.venv/bin/python -m autoreply.send_replies
./.venv/bin/python -m autoreply.send_replies --contact "联系人显示名"
```

显式向指定联系人发送：

```bash
./.venv/bin/python -m autoreply.send_replies --send --contact "联系人显示名"
```

发送器只发送每位联系人的最新 `generated` 草稿。每条回复会分别调用 `sendwechat.scpt`，
全部发送成功后草稿更新为 `sent`，对应原始消息更新为 `replied`。

如需覆盖命令或数据库位置：

```bash
AUTOREPLY_WECHAT_CLI="/absolute/path/to/wechat-cli" \
AUTOREPLY_DB_PATH="/absolute/path/to/messages.sqlite3" \
./autoreply/run_poll.sh
```

## 安装 cron

```bash
./autoreply/install_cron.sh
```

macOS 上需要确保执行 cron 的系统进程有权限读取微信数据；可先手动运行
`run_poll.sh` 验证。cron 每分钟唤醒一次是因为标准 cron 不支持 10 秒周期；活跃状态下，
同一个带锁进程会自行每 10 秒循环。

`new-messages` 自身仍只提供每个变化会话的最后一条摘要，因此脚本会继续调用 `history`
拉取游标之后的全部文本。微信历史接口只提供分钟级时间，脚本使用时间窗口重叠和唯一指纹去重。

自适应调度器每次成功插入新消息后，会只针对本轮出现新消息的个人联系人分别生成回复，
并通过 AppleScript 自动发送。每位联系人独立生成、独立发送、独立验证，不会群发，也不会发送
数据库里其他联系人的历史草稿。群聊、公众号、系统会话仍会被排除。

如果 Qwen 服务未启动或某位联系人发送失败，错误会写入轮询日志；其他联系人和后续微信消息抓取
不会因此中断。
