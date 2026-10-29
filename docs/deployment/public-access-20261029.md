# 2026-10-29 取消网站入口共享口令

按用户要求取消 https://zhiming.mom 入口的浏览器 Basic Auth 弹窗。此前该验证在应用中启用，使用共享用户名 `friend`，独立于个人账号系统。

当前服务基于 `8be21c0`，仅更新以下文件，生产模型配置、数据库、Nginx 和证书均未修改：

| 文件 | SHA256 |
| --- | --- |
| `/opt/zhiming/app/web.py` | `ea48c6f603cd29c95d6e1e6af370a15011ea86ff0bc3b63aa2ebcc8b377be735` |
| `/usr/local/lib/zhiming/launch.py` | `5291164e29a394ceefe10aa35c433347a162029304c463c7a10a62577f2b1a58` |

`create_web_app(public_origin=...)` 支持不设置共享口令，继续启用 HTTPS Cookie、Host 和精确 Origin 校验。显式设置 `share_password` 时仍要求 HTTPS 地址与至少 16 字符口令，兼容临时朋友分享。生产启动器仅传入 HTTPS 地址，不再读取 `/etc/zhiming/share-password`；该文件保留用于回滚。

部署前已执行 `zhiming-backup.service`，核对线上原文件哈希后保存回滚副本并原子替换，重启应用。服务器记录位于 `/var/lib/zhiming-deployment/public-access-20261029/`，发布元数据 `/etc/zhiming/release.json` 的 `local_patches` 标明此次补丁及文件哈希。

验证：

- 本地公开访问、可选口令分享、账号及网页接口回归：57 项通过；Ruff 检查及格式检查通过。
- 服务器经可信 HTTPS 访问 `/`、`/login`、`/privacy`、`/static/login.js`、`/api/account` 均返回 200，不含 `WWW-Authenticate`。
- 无口令访问注册接口：缺少必填参数返回 422，错误 Origin 返回 403；未创建线上测试账号。
- 本地公开 HTTPS 测试覆盖注册、退出、重新登录、Secure/HttpOnly/SameSite Cookie 和用户记录隔离。
- 管理员电脑从公网指定正式域名及新服务器 IP、保留完整 TLS 校验：首页、注册页、静态脚本及离线会话接口均返回 200，无 Basic Auth 挑战；会话 Cookie 保留 Secure、HttpOnly、SameSite=strict。
- 本次没有调用真实模型。

回滚时使用该目录的 `web.py.before`、`launch.py.before` 和 `release.before.json` 恢复原文件及原权限后重启应用即可；无需回退数据库。恢复旧启动器将重新启用网站入口口令。
