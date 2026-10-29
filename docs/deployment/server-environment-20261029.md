# 2026-10-29 新 Debian VPS 部署记录

本记录对应新服务器 `217.116.171.241:61234`，时间采用北京时间。应用、代理、模型、备份、SSH 隧道和正式 HTTPS 已部署验证。入口为 [https://zhiming.mom](https://zhiming.mom)；旧腾讯云服务器未操作。下文“未完成”段为签发前状态，后续完成情况见末尾 HTTPS 记录。

## 发布来源

| 项目 | 实际版本 |
| --- | --- |
| 应用提交 | `2e93e41f68d221189d404392802582ea89a996fc` |
| Git archive SHA256 | `3fae242b28363b5f4f465e3fc7877c37ad917db102ce82cfc2bb442fb6189a26` |
| 系统 / Python / uv | Debian 12 / 系统 CPython 3.11.2 / uv 0.13.0 |
| 依赖 | uv.lock 的 llm、web；40 个运行依赖及项目本身，pip check 41 个发行包通过 |
| 知识库 | `v1-984b14f53d4d43c7`，1171 条，451 模型审核、720 草稿、0 人工 |
| 数据库 | 新建业务库，schema 5，未迁移本机或旧服务器用户数据 |

部署前本地已有修改为 CHANGELOG.md、README.md、docs/README.md、docs/usage.md；未跟踪 docs/deployment.md、docs/deployment/、tests/web/test_birth_profile_navigation.py。全部保留，未提交、重置或覆盖新增测试。应用使用 HEAD 的 Git archive，未提交文档和测试未混入应用。

模型凭据仅从已授权本地 .env 提取 `DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL`，通过 SSH 标准输入原子写入 `/etc/zhiming/runtime.env`，root:root 0600。未打印密钥、上传完整 .env 或提交 Git。

复用本机离线包缓存，运行包以锁文件导出的 requirements 哈希校验；再用 `uv sync --frozen --no-dev --extra llm --extra web --offline --no-index --find-links ...` 安装项目。构建阶段补充 Hatchling 所需 tomlkit/editables，未修改锁文件。七项参考数据按提交中 manifest 的 SHA256 重新核验后构建知识库。未安装 dev 或 MCP。

## 资源、服务和配置

2 核、约 2GB 内存、20GB 系统盘；新增 1GiB `/zhiming.swap`，0600、已启用并写入 fstab，原 fstab 已留副本。部署后磁盘约 15GB 可用。没有系统全量升级、整机重启或重设防火墙。主机时区 US/Eastern，备份 timer 显式使用 Asia/Shanghai；检查时 NTP 同步为 no，未更改无关服务的系统时间设置。

实际部署配置保存在 [debian-20261029/](debian-20261029/zhiming.service)：

- 无特权系统账号 zhiming，无交互 shell、无 sudo；root 管理代码和 venv，仅业务数据、trace 和应用日志可写。
- 单进程监听 127.0.0.1:8765；systemd 开机启动、失败 5 秒重启、内存软限 640MiB/硬限 768MiB、Swap 限 512MiB。
- [launch.py](debian-20261029/launch.py) 是独立部署启动器，设置 30 秒优雅退出。验证时活动 SSE 曾使旧启动方式等待至 45 秒停止超时，因此显式约束；应用源码提交未改动。
- Nginx 独立 127.0.0.1:8080 代理，保留含端口 Host 和协议，关闭缓冲，420 秒读写超时。
- 新增精确匹配 zhiming.mom 的 HTTP 验证站点，仅开放 ACME 路径，其余 503，尚未把付费应用暴露到普通 HTTP。HTTPS 配置模板保存在 `/etc/zhiming/zhiming-https.conf.pending`。
- 原 Nginx 配置与默认 80 站点 SHA256 不变，只做 reload；nft 规则逐字未变，SSH 61234、x-ui、xray、其他监听均保留。
- 应用日志 `/var/log/zhiming/app.log`，每日轮转、7 份、14 天最大年龄、10MB 触发；Nginx 沿用现有每日 14 份轮转；trace 定时清理 7 天前文件。

## 验证结果

| 验证 | 结果 |
| --- | --- |
| 环境自检 | 所有必需项通过，依赖兼容性通过 |
| 页面 | 入口、问道、六体系页面、静态 JS 均 HTTP 200 |
| Cookie / 来源 | HttpOnly、SameSite=strict；正常 Origin 通过、错误 Origin 403、错误 Host 400、缺客户端头 403 |
| 排盘 | 合成生辰八字年辛巳/月己亥/日壬辰；星盘 10 天体及上升点、姓名五格、黄历通过 |
| 会话 / 历史 | 离线三张牌、原记录追问保持抽牌、历史查询通过 |
| SSE | Nginx 实时并发离线请求首事件 0.176 秒，4 个 data 事件，聊天结束前到达 |
| SSH 隧道 | 管理员电脑 127.0.0.1:18765 经 8080：页面、Cookie、八字、解读、历史、SSE、含端口 Origin 均通过 |
| 真实模型补测 | 配置模型 deepseek-flash，单张牌 28.56 秒，HTTP 200、submit_reading、非空输出、历史保存；首 SSE 1.44 秒、5 个 data 事件；测试身份已删除 |
| 备份恢复 | 在线备份非空库，提取后 integrity_check=ok、schema=5、合成解读可读取，未覆盖线上库 |
| 日志 | 已实际强制轮转，随后页面继续正常 |
| 重启 | 手动重启记录保留、旧 Cookie 按产品设计失效；SIGKILL 后自动恢复；服务与 timers 均 enabled |
| 清理 | 合成解读、画像、排盘、trace、5 条空身份租约已清理；2 个含合成记录的测试备份已删除，干净备份重新校验与恢复通过 |

首次真实请求也返回 HTTP 200，但验证脚本漏传 SSE 的 system=tarot，误等默认队列而超时，未保留响应断言。原报告的 model_api_called=false 为记录位置错误，不能据此声称没有付费调用。负责人额外授权一次后修正脚本，补测完整通过；没有扩大质量评测。模型列表 HTTP 200 只说明服务商公布该标识，不证明底层模型身份。既有模型质量与知识审核结论不变。

## 备份和证据

[backup.py](debian-20261029/backup.py) 使用 SQLite backup API 取得一致性快照，包含当前/历史知识库、配置与凭据、release.json、服务、启动器、锁文件及数据清单；每日北京时间 04:10 加 0–5 分钟随机延迟，7 天保留。每个归档提取业务库复查完整性并生成 SHA256。root 私有目录 `/var/backups/zhiming`，0700；归档含凭据且可能保留已清理合成记录至到期，禁止公开下载。异地目的地未提供。

服务器脱敏证据位于 `/var/lib/zhiming-deployment/`：doctor.json、smoke.json、stream.json、restart.json、model-live.json、final-audit.json；版本在 `/etc/zhiming/release.json`，包含实际部署配置逐文件 SHA256。本机材料位于忽略目录 `reports/server-deployment-20261029/`。

## 未完成

`zhiming.mom` 的 A 记录仍为 172.232.24.235、172.234.25.42、172.232.24.161，NS 为 dnsowl.com。已请求将 @ A 改为 217.116.171.241 并移除冲突记录；无域名后台授权，不能自行修改 DNS。服务器已安装 certbot，定时续期 enabled；尚未向 CA 发起失败签发。DNS 就绪后使用 webroot 签发，启用精确 HTTPS origin 与独立访问口令，验证公网 Cookie、长请求、SSE 和续期。已准备带 DNS 前置校验的 `/usr/local/lib/zhiming/activate-https.sh`，目前没有执行；不能将待执行脚本视为 HTTPS 已验收。

从管理员电脑使用 curl 的 resolve 参数直连新 IP 验证 `http://zhiming.mom/.well-known/acme-challenge/deployment-check` 返回指定标记，证明公网 80 可达且精确域名 vhost 生效；普通解析仍到旧 IP。HTTPS 激活后需重新交付入口：Secure Cookie 不适用于原普通 HTTP 隧道方式，公网域名应作为正式入口。

未整机重启，以免中断已有其他服务；开机启用和应用重启已验证。异地备份与 NTP 同步待后续维护。


## HTTPS 完成记录（当日后续）

用户在 NameSilo 将根域名 A 指向新 IP 后，权威 DNS、服务器查询的 1.1.1.1/8.8.8.8 以及服务器普通解析均返回 217.116.171.241，无 AAAA。

Let’s Encrypt YE2 正式证书签发成功，启用精确域名 Nginx 443 配置，80 对域名做 308 HTTPS 跳转，ACME webroot 验证路径保留。证书有效期至 **2027-01-27 03:51（北京时间）**。应用 ZHIMING_PUBLIC_ORIGIN=https://zhiming.mom，独立访问口令启用，用户名 friend；口令未写 Git，本机 invitation.txt 已限制仅当前用户与 SYSTEM 读取。

签发遇到服务器到正式 ACME 地址连接超时，IPv4/IPv6 均如此；测试地址可达。本机 IPv4 可达正式地址，故临时启动仅允许 acme-v02.api.letsencrypt.org:443 的 loopback CONNECT 转发，通过 SSH 反向 loopback 转发给服务器 certbot 使用；未中断 TLS、未绕过 CA 校验，私钥未离开服务器。签发后两端临时转发均关闭，服务器无 18081 监听，未持久保存代理环境变量。

公网验证从管理员电脑直连新 IP、保持正式域名 SNI/Origin/CA 校验，TLSv1.3、证书可信：

- HTTP 308 正确重定向；页面、静态文件、API 未授权或错误口令均 401。
- 九个页面及静态资源授权后 200，Secure/HttpOnly/SameSite=strict Cookie 和 no-store 通过。
- 八字、星盘、黄历、离线解读和历史读取通过；错误 HTTPS Origin、HTTP Origin、客户端头与 Host 被拒绝。
- SSE 保持连接超过 15 秒后实际收到心跳，再触发离线解读收到 4 个 data 事件和 done，总耗时约 20 秒；无付费模型调用。
- 服务器使用普通 DNS 与系统信任链访问通过，HTTPS 模式下服务重启成功，旧内存 Cookie 按产品设计失效。
- 测试身份、业务数据与 trace 清理，证书/账号私钥/续期钩子纳入 root 私有备份，干净库提取恢复和完整性检查通过。
- 原 Nginx 配置校验值、防火墙、SSH 61234、x-ui 等保持。

本机递归 DNS 尚有旧 A 缓存，因此外部测试报告明确记载 connect_ip_override=217.116.171.241，未冒称本机默认 DNS 已刷新。服务器默认 DNS/TLS 通过，CA 实际 HTTP 域名验证成功。等待本机 DNS 缓存到期后可直接使用正式入口。

certbot.timer 已启用；无临时代理条件下的 staging dry-run 全部成功，deploy hook 的 nginx 校验和 reload 实际执行成功。但服务器直连正式 ACME 接口仍超时，**未来正式自动续期存在风险**，不能以 staging 成功替代正式网络可用性。续期前需恢复出站连通性或配置可靠路径；未为掩盖该问题依赖持续运行的本机隧道。

脱敏证据新增 https.json（外部验证）与 https-server.json（服务器 DNS、重启、续期、清理及恢复），release.json 已改为 https_live_verified 并更新配置哈希。原应用提交不变。异地备份与 NTP 同步仍未配置。


## 当日后续版本切换

用户随后指定切换至 `afa6ffe`，本地与服务器均已完成。本文前述 `2e93e41` 为初始部署及真实模型验证版本；当前版本、离线回归、健康检查及回滚信息见 [afa6ffe 切换记录](upgrade-afa6ffe-20261029.md)。
