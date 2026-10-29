# 2026-10-28 服务器环境部署记录

> 历史记录：本文仅对应旧腾讯云 Ubuntu 服务器。2026-10-29 部署目标已更换，旧服务器活动 SSH 配置已删除，`zhiming-server` 现在指向新 Debian VPS。本文的环境、端口、模型验证与备份状态均不适用于新服务器；下方 SSH 隧道命令也不能据此用于访问新服务器上的网站。当前连接和部署状态见 [服务器部署说明](../deployment.md)。旧服务是否仍运行未在本次切换中检查。

## 范围与状态

本轮完成腾讯云 Ubuntu 24.04 服务器环境和仅本机访问的应用准备，域名正在申请。没有迁移开发电脑的 `.env`、访问口令、虚拟环境、业务数据库、用户记录或 SSH 私钥，没有调用付费模型，没有开放公网网站。

环境部署阶段未配置真实模型 API Key，随后于当日按用户提供的文件独立配置服务器凭据，并完成一次真实模型端到端验证。当前“入内”可以使用真实模型，“离线演示”继续可用。初始业务数据库为新库，验证只使用合成资料，测试身份已通过删除接口清理。备份中含环境阶段的合成测试记录，用于证明能够恢复非空业务数据。

## 版本与环境

| 项目 | 实际配置 |
| --- | --- |
| 系统 | Ubuntu 24.04.4 LTS，x86_64 |
| 内核 | 更新后重启至 `6.8.0-147-generic` |
| 时间 | Asia/Shanghai，NTP 已同步 |
| Python | uv 管理的 CPython 3.11.17；系统 Python 保持独立 |
| uv | 0.13.0，`/usr/local/bin/uv` |
| 代码提交 | `2e93e41f68d221189d404392802582ea89a996fc` |
| 源码归档 SHA256 | `3fae242b28363b5f4f465e3fc7877c37ad917db102ce82cfc2bb442fb6189a26` |
| 知识库 | `v1-984b14f53d4d43c7`，1171 条，451 条模型审核、720 条草稿、人工审核 0 条 |
| 依赖 | `uv.lock` 对应的 `llm`、`web` 依赖，未安装 dev/MCP；41 个已安装发行包兼容性检查通过 |
| 工具 | Git、curl、CA 证书、编译工具、系统 Python venv、Nginx、SQLite CLI、unzip、UFW |

源码来自上述提交的 Git archive，本机未提交的文档和测试未混入服务器代码。版本来源记录在服务器 `/etc/zhiming/release.json`。

服务器访问 PyPI 较慢，采用以下安装路径，未修改项目锁文件：

1. 在管理员电脑从 `uv.lock` 冻结导出 `llm`、`web` 的带哈希 requirements。
2. 按 Ubuntu x86_64、CPython 3.11 选择 40 个运行时依赖包，下载时逐项验证锁文件 SHA256；构建工具单独从 PyPI 获取并校验发布哈希。
3. 上传包缓存，用 `uv pip sync --require-hashes` 离线安装，再用 `uv sync --frozen --no-dev --extra llm --extra web --offline --no-index --find-links /opt/zhiming/cache/wheelhouse` 安装项目本身。
4. 七项固定参考数据同样在管理员电脑按清单核验后上传，服务器 `scripts.fetch_data` 再次核验全部哈希，然后构建知识库。

原始安装包、下载记录和校验材料位于管理员电脑忽略目录 `reports/server-environment-20261028/`；服务器保留离线包缓存 `/opt/zhiming/cache/wheelhouse/`。

## 账号与目录

应用使用无交互登录的系统账号 `zhiming`，无 sudo 权限。代码、解释器和运行配置由管理员管理，应用服务只允许写入业务数据与执行记录。

| 路径 | 用途 |
| --- | --- |
| `/opt/zhiming/app` | 提交对应的源码、`.venv`；`data`、`runs` 为下方目录的符号链接 |
| `/opt/zhiming/data` | 新业务库、当前知识库、历史知识快照、参考数据 |
| `/opt/zhiming/runs` | 应用 trace |
| `/opt/zhiming/python` | uv 管理的 Python |
| `/opt/zhiming/tools` | 安装工具环境 |
| `/opt/zhiming/cache` | 下载、构建缓存及环境自检报告 |
| `/etc/zhiming/runtime.env` | systemd 环境文件，已独立配置模型密钥与接口地址，权限 root:root 0600 |
| `/etc/zhiming/share-password` | 服务器独立生成的未来公网访问口令，root:zhiming 0640，不写入本文或 Git |
| `/var/backups/zhiming` | 本机备份，root:root 0700 |
| `/var/lib/zhiming-deployment/smoke.json` | 部署冒烟验证摘要，无凭据 |

## 服务、网络与日志

- [zhiming.service](zhiming.service)：单进程应用，`127.0.0.1:8765`，开机启动、异常重启、45 秒退出等待；启用文件系统写入限制。
- [zhiming-local.conf](zhiming-local.conf)：Nginx 仅监听 `127.0.0.1:8080`，转发至应用，保留 Host 与协议信息，关闭响应缓冲，代理读写超时 420 秒。
- UFW：默认拒绝入站、允许出站，目前只放行 TCP 22（IPv4/IPv6）。未修改现有 SSH 密钥或云控制台防火墙。
- 应用日志使用 journald，系统日志总量上限 300MB、运行时 100MB、最长 14 天；配置为 `/etc/systemd/journald.conf.d/zhiming-retention.conf`。
- Nginx 使用 `/var/log/nginx/zhiming-*.log`，受系统 `/etc/logrotate.d/nginx` 管理。

管理员可通过 SSH 隧道体验：

```powershell
ssh -N -L 18765:127.0.0.1:8080 zhiming-server
```

保持该窗口运行，在浏览器打开 `http://127.0.0.1:18765` 并选择“离线演示”。现阶段通过 SSH 隧道限制访问，未启用公网 Basic Auth；域名就绪后须同时配置应用 `--public-origin`、`--share-password-file`、Nginx HTTPS 和云/主机防火墙，再验证 Secure Cookie。

常用管理命令，在 SSH 登录后执行：

```bash
sudo systemctl status zhiming nginx
sudo journalctl -u zhiming -n 100 --no-pager
sudo systemctl restart zhiming
sudo nginx -t
sudo systemctl status zhiming-backup.timer
sudo systemctl start zhiming-backup.service
sudo journalctl -u zhiming-backup.service -n 20 --no-pager
sudo ss -lntp
sudo ufw status verbose
```

真实模型配置使用 `sudoedit /etc/zhiming/runtime.env`，填写服务器独立的 `DEEPSEEK_API_KEY` 和所需 `DEEPSEEK_BASE_URL` 后重启应用。密钥不放到命令行、不写入 Git，也不在日志中打印。实际模型可用性和质量需要另行验证。

## 备份与恢复

[备份脚本](backup.py) 安装于 `/usr/local/lib/zhiming/backup.py`，由 [备份服务](zhiming-backup.service) 和 [定时器](zhiming-backup.timer) 执行。每日北京时间 04:10 起随机延迟最多 5 分钟，保留 7 天；本轮已手动执行成功。

备份使用 SQLite 在线备份接口生成一致性快照，包含业务库、当前与历史知识库、服务器运行配置、备份脚本、应用配置、依赖锁与数据清单。每次生成后从归档中提取数据库到临时目录，执行 `PRAGMA integrity_check`，并生成归档 SHA256。

固定参考数据可按清单重建，未重复放入每日归档。trace 未纳入每日备份。备份可能含模型凭据和访问口令，必须保持 root 私有，不公开下载。备份保留 7 天，与在线身份闲置 12 小时自动清理分别执行；用户删除在线记录后，已有备份可能继续保留至备份期限。

恢复步骤：

1. 选定备份并核对对应 `.sha256`，确认其提交号、知识库版本和运行配置适合恢复目标。
2. 停止 `zhiming.service`，将当前数据库另做安全备份。
3. 在 root 私有临时目录提取归档，检查数据库完整性、schema 及所需历史知识快照。
4. 恢复数据库到 `/opt/zhiming/data/app.db`，处理已停止服务的旧 WAL/SHM，恢复所需知识库版本，并将业务目录权限设回应用账号。
5. 按需恢复运行配置；当前备份里的代码配置归档路径保留了 `/opt/zhiming/app/` 层级。安装与提交匹配的源码和依赖。
6. 启动应用并验证页面、记录及计算。当前实现不会因为恢复数据库而恢复重启前的浏览器身份或未完成任务。

本轮恢复验证从真实归档中提取了包含合成解读的数据库，确认解读记录存在、schema 为 5、完整性检查通过。没有覆盖在线数据库。异地备份目的地尚未配置，本机备份无法抵御整机或磁盘丢失。

## 验证结果

- 系统更新完成，内核更新后已重启；系统时间同步、磁盘、内存、Swap 和 SSH 正常。安装服务后再次整机重启，确认应用、Nginx、备份定时器均自动启动，UFW 规则保持有效，无失败的 systemd 单元。
- 项目环境自检 19 项必需检查全部通过，41 个已安装发行包兼容性检查通过。
- 12 组部署冒烟检查通过：页面和静态资源、身份与 Cookie、八字、星盘、姓名、黄历、离线塔罗、Nginx SSE、原记录追问、来源/Host 校验、在线备份与恢复读取、合成身份清理。
- 最后一次整机重启后的完整冒烟于北京时间 2026-10-28 23:31:29 通过。另从管理员电脑实际建立 SSH 隧道，页面、离线身份、带 Origin 的黄历请求和身份删除均返回 HTTP 200；测试隧道已关闭。
- 本轮没有进行真实模型调用、公网 HTTPS 验证或全量测试；结论仅覆盖服务器环境和离线业务链路。

## 模型凭据配置与验证（当日后续）

根据用户提供的本机凭据文件，仅提取 `DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL`，通过加密 SSH 标准输入传递，在服务器原子写入 `/etc/zhiming/runtime.env`。文件权限保持 root:root 0600，密钥没有写入命令行、部署文档、Git 或验证摘要。接口地址只保存在服务器运行配置中。

模型列表探测返回 HTTP 200，确认现有 `deepseek-flash` 可用，因此没有修改项目 `config.yaml` 或单 Agent 模式。探测结果只是服务商报告的可用模型标识，不证明底层模型身份。

重启应用后，于北京时间 2026-10-28 23:56:55 完成一次真实模型验证，耗时 53.33 秒，结果如下：

- 配置模式身份创建和聊天接口均返回 HTTP 200。
- 合成的一张牌塔罗请求以 `submit_reading` 成功结束，解读及记录已保存。
- 历史记录查询与 Nginx SSE 进度流验证通过。
- 测试身份及其在线业务数据已通过应用删除接口清理。
- 已产生实际模型调用费用；未进行全量质量评测，既有质量验收结论不变。

脱敏验证摘要位于服务器 `/var/lib/zhiming-deployment/model-live.json`。模型凭据变更后已执行包含服务器配置的本机备份。

## 下一步

1. 服务器独立模型凭据和一次真实端到端验证已完成；后续按实际使用监测限流、费用和失败率。
2. 域名与备案准备完成后配置 DNS、HTTPS、访问口令和准确公网 Origin，核对云防火墙并开放主机 80/443。
3. 从外网验收长请求、SSE、Cookie 和访问验证，进行少量并发实测。
4. 确定异地备份目的地及对外服务许可。真实模型质量与知识库审核仍遵守项目原有未通过结论。
