# 运维：监控告警、全站费用控制与管理页

本说明对应 `ops/` 与 [`deployment/ops-20261030/`](deployment/ops-20261030/)。目标是不再靠手动检查发现故障：网站不可用、模型错误率升高、费用异常、磁盘不足、备份失败和证书将到期都会主动告警；全站每日预算、模型并发上限和异常消耗自动暂停在应用内强制执行；管理员在 `/admin` 网页查看状态并操作。

## 组成

| 部分 | 运行位置 | 作用 |
| --- | --- | --- |
| `/healthz` | 应用 | 公开健康检查，只返回 `{"status":"ok"}`（数据库可读）或 503，不含其他信息 |
| 费用控制（`memory/costs.py`） | 应用，与账号额度同一事务 | 每日预算、并发上限、异常消耗自动暂停、账号暂停与追加额度、全站用量台账 |
| `/api/ops/metrics` | 应用 | 只接受本机（127.0.0.1）且带 `Authorization: Bearer <ZHIMING_MONITOR_TOKEN>` 的请求，供监控读取错误率、预算与暂停状态；其余一律 404 |
| `/admin` 管理页 | 应用 | 仅 `ZHIMING_ADMIN_IDS` 中列出账号 ID 的账号可见，其余账号返回 404 |
| `ops/monitor.py` | 服务器 systemd 定时器，每 5 分钟 | 服务器侧检查、告警去重与发送、写 `/var/lib/zhiming-monitor/status.json` 供管理页显示 |
| `.github/workflows/uptime.yml` | GitHub Actions，每 10 分钟 | 从服务器之外探测公网可用性与证书，服务器整机宕机也能告警 |

## 告警

### 检查项与默认阈值

| 检查 | 来源 | 警告 | 严重 |
| --- | --- | --- | --- |
| 本机服务 / 公网访问 | `GET /healthz` | 响应超过 5 秒 | 无法访问或非 200 |
| 证书到期 | 与 `zhiming.mom:443` 完整 TLS 握手（校验证书链） | 少于 21 天 | 少于 7 天、校验失败或握手失败 |
| 磁盘空间 | `/`、`/opt/zhiming/data`、`/var/backups/zhiming`（同一磁盘只算一次） | 可用低于 15% 或 2 GiB | 低于 8% 或 1 GiB；所有路径都无法读取 |
| 备份 | 最新已完成的 `zhiming-*.tar.gz`（重新计算 SHA256 与 `.sha256` 比对；归档与摘要文件都不变时才沿用上次结果，“缺少摘要”等暂时状态不缓存）与 `zhiming-backup.service` 结果 | 缺少 SHA256 文件 | 超过 26 小时无新备份、服务失败、无备份、归档过小、摘要文件格式错误或摘要不一致（归档损坏）、备份目录不可读 |
| 应用指标采集 | `/api/ops/metrics` 能否读取并解析 | — | 连续 2 次失败（令牌不一致、接口报错、数据无法识别）；未配置令牌时立即严重。此时下面五项模型与费用检查显示“未知”，并已打开的问题保持打开 |
| 系统服务 | `systemctl is-active zhiming nginx` | — | 任一未运行；无法调用 systemctl（服务监控失效） |
| 定时任务 | 备份、trace 清理、certbot 定时器 | 未启用 | — |
| 自动重启 | `zhiming.service` 的 NRestarts | 两次检查间自动重启 ≥ 3 次 | — |
| 时间同步 | `timedatectl` NTPSynchronized | 未同步 | — |
| 模型错误率 | 近 30 分钟全站模型请求（至少 5 次才判定；页面关闭等取消不计） | ≥ 10% | ≥ 25% |
| 今日预算 | 今日用量 / 每日上限，及应用记录的“预算拒绝”事件 | ≥ 80% | ≥ 100%，或已开始因预算拒绝调用（余量不足一次调用的最小预留时，不到 100% 也会拒绝）；剩余预算重新足够容纳被拒绝的调用（例如提高预算）或次日零点后解除，修改无关设置不会解除 |
| 模型暂停 | 全站暂停状态 | 管理员手动暂停 | 异常消耗自动暂停 |
| 消耗突增 | 近 1 小时 token 与 7 天小时均值 | 超过均值 4 倍且超过 200,000 | — |
| 账号自动暂停 | 近 24 小时单账号异常消耗事件 | 有 | — |

阈值都可在 `/etc/zhiming/monitor.env` 调整，见 [`monitor.env.example`](deployment/ops-20261030/monitor.env.example)。

### 何时发送

- 问题出现时发一次；加重（警告→严重，包括严重→警告→严重的再次加重）立即再发；持续未解决时每 6 小时提醒一次；恢复正常时发一次“已恢复”。恢复后再次出现算新问题，即使上一次的恢复消息未送达，也会立即告警。
- 每个渠道分别记录“已告知的状态”。消息只有在该渠道发送成功后才算告知；失败的新问题、加重、提醒和恢复在下一轮（5 分钟后）对该渠道重试，直到成功。一个渠道失败不影响其他渠道，已成功的渠道也不会重复收到。失败原因只记录渠道名和异常类型，不记录地址或密钥。
- 同一轮的多个问题合并成一条消息。
- 未配置任何渠道时，告警只写入 `journalctl -u zhiming-monitor`，管理页“监控告警”会显示“未配置告警渠道”。
- “未知”只用于暂时无法判断的项目（例如指标采集第一次失败），不视为恢复，已打开的问题保持打开；采集链路本身的故障由“应用指标采集”检查告警，不会静默失效。

### 渠道

在 `/etc/zhiming/monitor.env`（root:root 0600）中任选：

- 企业微信 / 钉钉 / 飞书机器人：`ZHIMING_ALERT_WEBHOOK_KIND=wecom|dingtalk|feishu` 与 `ZHIMING_ALERT_WEBHOOK_URL`；钉钉、飞书开启“加签”时填 `ZHIMING_ALERT_WEBHOOK_SECRET`。机器人返回错误码（如关键词不匹配）按发送失败处理。
- Server酱（微信推送）：`ZHIMING_ALERT_SERVERCHAN_KEY`。
- 邮件：`ZHIMING_ALERT_SMTP_*`，465 端口用 SSL，其他端口用 STARTTLS。
- 通用 JSON Webhook / Slack：`generic`、`slack`。

配置后以 root 执行 `python3 -I /usr/local/lib/zhiming/monitor.py --test-alert` 确认能收到。监控程序会自行读取 `/etc/zhiming/monitor.env`（已设置的环境变量优先；`--env 路径` 可指定其他文件），因此手动运行与定时器运行使用同一份配置。

### 监控自身失效

- `ZHIMING_MONITOR_HEARTBEAT_URL` 填一个“心跳”地址（例如 healthchecks.io 免费检查，周期 5 分钟、宽限 10 分钟）：每轮检查完成后访问一次；监控停止或服务器宕机时由对方告警。
- 管理页在监控报告超过 15 分钟未更新时显示警告。
- GitHub Actions 的 `uptime` 工作流从外部每 10 分钟探测 `/healthz`、`/login` 与证书。它只在默认分支（`main`）上按计划运行；告警渠道使用仓库 Secrets（`ZHIMING_ALERT_WEBHOOK_URL`、`ZHIMING_ALERT_WEBHOOK_SECRET`、`ZHIMING_ALERT_SERVERCHAN_KEY`）与变量（`ZHIMING_ALERT_WEBHOOK_KIND`、`ZHIMING_UPTIME_URL`）。探测失败时运行失败，GitHub 也会按账号通知设置发送失败邮件。GitHub 定时任务可能延迟十几分钟，需要更及时可另外接入 UptimeRobot 等外部拨测，关键词设为 `"ok"`、地址 `https://zhiming.mom/healthz`。

## 全站费用控制

只作用于登录账号的真实模型调用；访客离线演示、排盘、姓名五格计算和历史记录不受影响。每次模型请求（含重试、安全分类、审校等辅助调用）都先在数据库事务中预留 token，同时检查以下规则，返回后按服务商实际用量结算：

| 规则 | 行为 | 默认（config.yaml） |
| --- | --- | --- |
| 全站每日 token 上限 | 剩余不足时先缩小本次输出上限，仍不足 256 token 则拒绝，次日零点（北京时间）恢复；当天首次用尽记录事件并告警 | 3,000,000 |
| 全站每日估算费用上限 | 与 token 上限同时生效；须填写输入、输出单价；未结算的预留按较高单价计算 | 不限 |
| 模型并发上限 | 全站同时进行的模型请求；超出时按到达顺序排队，超过等待时间提示稍后重试 | 6，排队 30 秒 |
| 异常消耗自动暂停（全站） | 10 分钟内全站消耗（含本次预留）超过阈值，立即暂停全站模型调用并告警 | 600,000 |
| 异常消耗自动暂停（单账号） | 超过阈值只暂停该账号 | 关闭（免费额度已限制单账号） |
| 自动恢复 | 自动暂停后多少分钟自动恢复；0 表示须管理员恢复 | 0 |

说明：

- 用量来自服务商返回的 usage；取消、超时或缺少 usage 的调用按预留量计入，宁可多算。金额是按配置单价的估算，不等于账单。
- 全站台账 `site_usage` 不随账号注销删除（只清除账号关联），注销账号不能“退回”当日预算。台账保留 90 天，费用事件 180 天，管理操作记录 365 天。
- 管理员恢复后，异常检测窗口从恢复时刻重新计算，不会因窗口内旧消耗立即再次暂停。
- 管理页修改的设置保存在数据库，覆盖 `config.yaml` 的默认值；“恢复为配置文件默认值”会清除全部覆盖。修改并发上限立即生效。
- 金额上限默认未启用：`config.yaml` 中单价与每日估算费用上限均为 0。上线前请在管理页按服务商实际价格填写单价和金额上限。
- 并发闸门在应用进程内计数，适用于当前的单 worker 部署；若改为多进程或多台服务器，需要改为共享的并发控制。
- 用户看到的提示：全站暂停或预算用尽为可重试（HTTP 503 或对话内提示，附带离线功能仍可用的说明）；账号被暂停为不可重试，提示联系管理员。

## 管理页 `/admin`

管理员是在 `/etc/zhiming/runtime.env` 的 `ZHIMING_ADMIN_IDS` 中列出**账号 ID**（`acct-…`，逗号分隔）的普通账号。权限绑定在不会复用的账号 ID 上，而不是账号名：管理员注销后，别人重新注册同名账号不会获得任何权限，重启后也不会；要授权新账号，需重新执行安装脚本（或 `python -m ops.admin resolve 账号名` 查询 ID 后写入）。配置账号名会在启动时被拒绝。启动时若列出的 ID 已无对应账号，会在应用日志中警告。先在网站注册该账号并设置强密码，再授权并重启服务。未登录访问 `/admin` 会跳转登录页；其他账号看到 404。所有修改请求沿用站点的 Origin 与 `X-Zhiming-Client` 校验，并写入操作记录。

页面内容（每 30 秒自动刷新）：

- **状态**：模型服务运行/暂停、今日用量与预算进度、估算费用、近 30 分钟错误率、并发与排队、服务器监控结果。
- **监控告警**：服务器监控各检查项、告警渠道与最近发送失败、近 24 小时费用事件（自动暂停、预算用尽等）。
- **用量**：近 24 小时每小时 token 柱状图（悬停显示数值，含失败调用的小时以斜纹区分，另有表格视图）、今日用量最多的账号。
- **费用控制**：一键暂停/恢复全站模型调用；修改每日预算、单价、并发、异常阈值、自动恢复。
- **账号**：搜索、查看今日与累计用量、暂停或恢复账号的模型调用、追加或收回额度（只调整追加部分，不低于免费额度）、强制下线全部设备。
- **系统**：进程启动时间、实例、内存中的会话、账号数、数据盘可用空间、`/etc/zhiming/release.json` 中的版本、管理操作记录。

## 部署步骤

在已按 [部署说明](deployment.md) 升级到包含本功能的代码后，以 root 登录服务器：

1. 在网站注册管理员账号（例如 `站长`），设置强密码。
2. 执行安装脚本（只安装与写入配置，不打印任何密钥）：

   ```bash
   bash /opt/zhiming/app/docs/deployment/ops-20261030/install-ops.sh 站长
   ```

   脚本会：备份将被替换的 `launch.py`、`backup.py`、`runtime.env`、`monitor.env` 到 `/var/lib/zhiming-deployment/ops-<时间>/`；安装 `monitor.py`、新启动器、增加监控文件的备份脚本和 `zhiming-monitor.service/.timer`；以应用账号只读查询管理员账号名对应的账号 ID（账号不存在则中止）；在 `runtime.env` 写入 `ZHIMING_ADMIN_IDS`（并删除旧的 `ZHIMING_ADMIN_USERS`）与随机 `ZHIMING_MONITOR_TOKEN`，在 `monitor.env` 写入同一令牌；重启应用、等待 `/healthz`、启用定时器并运行一轮。
3. 编辑 `/etc/zhiming/monitor.env` 填写告警渠道和心跳地址，执行 `python3 -I /usr/local/lib/zhiming/monitor.py --test-alert`。
4. 登录 `https://zhiming.mom/admin` 确认页面、监控报告和费用设置；按服务商价格填写单价，按预期流量调整每日预算。
5. 在 GitHub 仓库设置 `uptime` 工作流所需的 Secrets 与变量。合并本 PR 到 `codex/server-20261030` 不会启用外部定时探测：工作流需进入默认分支 `main`，且服务器已部署带 `/healthz` 的版本，再在 Actions 页面手动运行一次确认。
6. 部署环境验收：外部探测失败与恢复、告警真实收件、加重与恢复消息在渠道失败后的重试、令牌错误时“应用指标采集”告警、预算拒绝告警、异常消耗自动暂停与恢复。

常用命令：

```bash
systemctl list-timers zhiming-monitor.timer --no-pager
journalctl -u zhiming-monitor -n 50 --no-pager
python3 -I /usr/local/lib/zhiming/monitor.py --dry-run
cat /var/lib/zhiming-monitor/status.json
```

## 回滚

1. `systemctl disable --now zhiming-monitor.timer`。
2. 从 `/var/lib/zhiming-deployment/ops-<时间>/` 复制回 `launch.py`、`backup.py` 与 `runtime.env`，按原版本回退代码后 `systemctl restart zhiming`。
3. 新增的数据库表（`site_usage`、`site_settings`、`site_events`、`account_controls`、`admin_audit`）不影响旧版本运行，可保留。

## 验证记录

本次变更在开发环境完成离线验证：费用控制、并发闸门、管理接口权限（含管理员注销后同名注册）、按渠道的告警重试、指标采集失败、备份摘要校验与预算拒绝告警均有回归测试（`tests/web/test_cost_control.py`、`tests/tooling/test_monitor.py`），管理页在桌面与手机宽度、浅色与深色下渲染检查无横向滚动和脚本错误。未调用真实付费模型；开发环境无法访问生产服务器，尚未在 VPS 上安装与实测，部署后按上面的步骤 3–6 验证。
