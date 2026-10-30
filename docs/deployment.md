# 服务器部署说明

## 当前状态（2026-10-30，北京时间）

知命已部署到新 Debian VPS，正式入口为 **[https://zhiming.mom](https://zhiming.mom)**。页面、排盘、会话、实时 SSE、历史、一次获准的真实模型补测、HTTPS、备份恢复和服务重启均通过。旧服务器未操作，用户数据未迁移。

| 项目 | 实际配置 |
| --- | --- |
| 服务器 / 管理 SSH | 217.116.171.241，root，TCP 61234 |
| 资源 | Debian 12，2 核、约 2GB 内存、20GB 磁盘，新增 1GiB Swap，约 15GB 磁盘可用 |
| 应用提交 | 8be21c058044d07fb7a63e8eb515ed4d25e8005f |
| 源码归档 SHA256 | 300815cfba06e7483ca52cdaff1a9ac82eff9789a4fecc2d67c20325a72b970e |
| Python / uv | Debian CPython 3.11.2 / uv 0.13.0；锁定 llm、web 运行依赖 |
| 知识库 | v1-984b14f53d4d43c7，1171 条 |
| 服务 | 无特权 zhiming，单进程 127.0.0.1:8765；Nginx 127.0.0.1:8080 |
| HTTPS | Let’s Encrypt YE2，TLS 1.2/1.3；证书到期 2027-01-27 03:51（北京时间） |
| 模型凭据 | 独立 /etc/zhiming/runtime.env，root:root 0600，未写入 Git |
| 数据 | 保留现有业务库，schema 5，新增账号、出生资料、trace 清理、账号额度与注册限制表；未复制旧服务器或本机用户数据 |
| 备份 | 每日北京时间 04:10 后随机延迟最多 5 分钟，一致性快照，保留 7 天 |

当前版本来自 PR #27 合并并修复后的 `8be21c0` Git archive，保留现有业务数据及生产模型配置；账号登录、访客记录导入、导出、排盘及实时 SSE 验证通过，详见 [8be21c0 升级记录](deployment/upgrade-8be21c0-20261029.md)。本次未调用真实模型；此前 `37fb626` 的真实模型验证见 [大运步数耗尽修复与验证](verification/dayun-recovery-20261029.md)。[afa6ffe 版本切换记录](deployment/upgrade-afa6ffe-20261029.md) 仅适用于该次历史升级。实际部署配置在 [debian-20261029/](deployment/debian-20261029/zhiming.service)，详见 [初始部署记录及验证结果](deployment/server-environment-20261029.md)。[旧腾讯云记录](deployment/server-environment-20261028.md) 仅供历史参考。

## 访问

服务器代码快照保存在 GitHub 分支 [`codex/server-20261030`](https://github.com/stanGSA/ZhiMing/tree/codex/server-20261030)，从实际部署基线 `8be21c0` 创建。分支包含线上源码、无密钥的 `config.yaml`、回归测试与部署说明；1,107 个服务器文件完成 SHA256 核对，运行源码、模型配置和锁文件与线上一致，文档与回归测试另作更新。差异文件及核对范围见[源码快照清单](deployment/server-source-20261030.json)。生产环境变量、用户数据库、日志、私钥与证书不在分支中。

2026-10-30 已上线账号额度与注册限制：每个账号累计免费 250,000 Token，输入与输出合计（含缓存输入），不按月重置。原有账号从本次上线获得完整额度，不追溯历史消耗。同一 IP 下同一设备在滚动 7 天内只允许注册一个账号，同一 IP 的其他设备可以注册；设备通过签名浏览器 Cookie 识别，清除 Cookie、更换浏览器或无痕窗口可能绕过识别。额度不足时拒绝新的模型调用，离线演示、直接排盘与历史访问保留。详见[免费额度及注册限制部署记录](deployment/free-quota-20261030.md)。

打开 [知命正式入口](https://zhiming.mom) 默认显示账号登录，2026-10-29 已按要求取消浏览器弹出的 `friend` 共享访问口令。用户可注册、登录个人账号后使用大模型；保留访客入口，但访客仅能使用离线演示。手机及窄屏优先显示登录表单。详见[账号与访客访问控制](deployment/account-demo-access-20261029.md)。

当前以 `8be21c0` 为基线，额外部署公开访问补丁：HTTPS 地址不再强制要求共享口令，生产启动器仅传入 `public_origin`。服务器 `/etc/zhiming/release.json` 的 `local_patches` 记录实际文件 SHA256，详见[取消入口口令记录](deployment/public-access-20261029.md)。旧共享口令文件保留但不再被生产启动器读取；历史 invitation.txt 中的访问方式已失效。临时朋友分享脚本仍可单独启用共享口令。

登录账号后可选择真实模型或离线演示，访客直连功能页也只创建离线会话，直接请求切换真实模型返回 403。HTTPS 使用 Secure、HttpOnly、SameSite=strict Cookie，精确 Origin 为 `https://zhiming.mom`。此前普通 HTTP 隧道不适用于启用 Secure Cookie 后的浏览器访问。

权威 DNS 和服务器递归解析已为 217.116.171.241，未发现 AAAA。管理员电脑的本地递归缓存仍可能暂时返回旧 IP；公网验证使用指定新 IP、保留正式域名 SNI 和完整 CA 校验，未关闭证书校验。服务器普通 DNS/TLS 访问也已验证。如果本机仍显示旧站点，等缓存 TTL 到期后刷新，避免向旧站点输入口令。

管理登录：

```powershell
ssh zhiming-server
ssh titi
# 其他已配置相同专用密钥的客户端：
ssh -i ~/.ssh/zhiming_vps_ed25519 -p 61234 root@217.116.171.241
```

专用私钥仅留管理员电脑。裸连接可能未选中该密钥，优先使用已配置的别名。

## 运维命令

SSH 登录后：

```bash
systemctl status zhiming nginx --no-pager
systemctl restart zhiming
tail -n 100 /var/log/zhiming/app.log
nginx -t
systemctl status zhiming-backup.timer zhiming-trace-retention.timer --no-pager
systemctl start zhiming-backup.service
journalctl -u zhiming-backup.service -n 20 --no-pager
cat /etc/zhiming/release.json
ss -lntp
free -h
df -h /
```

监控告警、全站费用控制与 `/admin` 管理页的安装、检查项和回滚见[运维说明](operations.md)（安装脚本 `deployment/ops-20261030/install-ops.sh`，待部署）。

应用开机启动、失败 5 秒重启；内存软限 640MiB、硬限 768MiB，Swap 上限 512MiB。root 管理代码和启动器，应用只写业务数据、trace 和自身日志。Nginx 公网 80 对该域名重定向 HTTPS，443 反代应用；代理保留 Host、协议并关闭缓冲，超时 420 秒。原 Nginx 默认站点、无关服务、防火墙规则和 SSH 61234 均保留。

应用日志每日轮转、7 份，trace 保留 7 天；Nginx 沿用原有每日 14 份轮转。服务重启会结束内存访客身份；新版账号登录令牌存入数据库，可在重启后恢复身份并跨设备访问账号记录。访客闲置 12 小时清理规则不变；升级前访客历史的恢复方案尚待讨论，本次未认领、迁移或删除原有访客记录。

模型字段及 ZHIMING_PUBLIC_ORIGIN 独立保存在 /etc/zhiming/runtime.env；用安全编辑器维护后重启，禁止打印或写入 Git。

## 备份恢复

/var/backups/zhiming 为 root:root 0700。归档包含在线一致性业务快照、当前/历史知识库、运行凭据、发布版本、启动器、服务、代理配置、证书及 ACME 账号私钥、续期配置和钩子、锁文件和数据清单。每次独立提取数据库检查 integrity_check 并生成 SHA256。已验证非空数据库恢复读取；部署收尾已移除含合成记录的测试备份，干净备份再次恢复验证通过。后续业务备份可保留已删除数据至 7 天到期，且含凭据，不可公开下载。

恢复会覆盖当前业务库，先确认恢复点和数据取舍：

1. root 私有目录校验归档 SHA256，核对其中 release.json 的提交号。
2. 停止 zhiming，先对当前库另做一致性备份。
3. 从归档提取 app.db 到临时目录，检查完整性和 schema；准备匹配提交及锁定依赖。
4. 停止状态下恢复 /opt/zhiming/data/app.db，处理旧 WAL/SHM，恢复所需知识快照，业务目录权限为 zhiming:zhiming。
5. 按需恢复运行配置并校验 Nginx，启动后验证页面、历史和排盘。恢复数据库不会恢复进程内会话。

异地目的地尚未提供，同盘备份无法抵御整机丢失。参考数据按固定清单重建，未重复加入每日归档。

## 证书续期与剩余事项

`zhiming.mom` 的 @ A 已指向 217.116.171.241，DNS 由用户在 NameSilo 修改。正式证书已签发并启用，HTTP 308 跳转 HTTPS；共享访问口令取消后，公网入口直接返回 200。实际 HTTPS 校验与约 20 秒 SSE 心跳/进度链路通过，无新增付费模型调用。

certbot.timer 已启用，`certbot renew --dry-run --cert-name zhiming.mom --no-random-sleep-on-renew` 成功，续期 deploy hook 执行 nginx -t 后 reload，也已实际验证。证书到期为 2027-01-27 03:51（北京时间）。

**正式自动续期仍有网络限制：服务器直连 Let’s Encrypt 正式 ACME 接口在 IPv4/IPv6 均超时，测试接口可达。** 初次签发通过临时、仅限正式 ACME 主机的本机 CONNECT 转发，经 SSH 反向隧道完成；TLS 端到端校验，证书私钥始终在服务器。临时转发和隧道已关闭，未保存代理环境变量。测试环境续期成功不能证明未来正式续期能连接成功，需要在续期前恢复服务器到正式 ACME 接口的出站连通性，或另行配置可靠出站路径。

异地备份、NTP 同步仍待后续处理；未整机重启以保留其他服务，已验证开机启用配置和应用异常恢复。项目既有模型质量、知识库审核未通过结论不因部署改变。
