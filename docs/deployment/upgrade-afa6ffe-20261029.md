# 2026-10-29 切换至 afa6ffe

服务器 `217.116.171.241` 与本地分支 `codex/validation-retry-fixes` 均已切换到用户指定版本：

- 提交：`afa6ffe9a2f00faeafeb9b261c872a009d8d83b5`。
- 提交说明：`fix: preserve citation retry limits and recover unfinished readings`。
- 源码归档 SHA256：`7fa70714a24988c5a68b63b74393927df507f2db0c8468535d53907d84afad22`。
- 上一版本：`2e93e41f68d221189d404392802582ea89a996fc`。

## 范围与执行

目标是当前提交的后续版本，涉及引用边界、引用反馈、重复失败次数及未完成解读恢复；pyproject.toml、uv.lock、业务库 schema、知识库、网页接口与配置未变。

本地使用 `git merge --ff-only afa6ffe` 快进，切换前后未提交 tracked diff 逐字相同；未跟踪的部署材料和 tests/web/test_birth_profile_navigation.py 保留。部署文档随后按新版本更新，未提交这些本地改动。

服务器从指定提交 Git archive 准备候选目录，复用已锁定且不变的运行依赖，环境自检全部必需项通过，41 个发行包兼容性检查通过。切换前执行在线一致性备份，再短暂停止应用、切换代码目录并启动。没有覆盖 data/runs、凭据、Nginx、证书或防火墙，没有数据库迁移或旧服务器操作。

旧代码及原虚拟环境保留在 `/opt/zhiming/rollback-2e93e41-20261029`；旧目录的 data/runs 是指向现有数据的链接，不是旧业务库副本。切换脚本带失败回退；本次健康检查通过，未触发回退。服务重启按产品设计结束内存身份，用户需刷新重新开始。

## 验证

本地离线回归 **65 passed，67.89 秒**：

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/harness/test_reference_boundary.py tests/harness/test_loop_and_guard.py tests/agents/test_specialist_state_recovery.py tests/runtime/test_reference_recovery.py tests/web/test_web_api.py
```

服务器逐项比较归档中的 **1095 个源码文件**，均与 /opt/zhiming/app 一致。HTTPS 证书信任链、入口与八个页面/资源、Secure Cookie、八字、离线单张塔罗、历史读取、SSE 完成及错误 Origin 拒绝通过；合成测试数据通过删除接口清理。切换后再次执行备份。

管理员电脑另外通过公网直连新 IP、保持正式域名 SNI/Origin 与 CA 校验验证：HTTP 308、访问口令、页面、Secure Cookie、八字/星盘、历史及实时 SSE 均通过；SSE 实际收到 15 秒心跳及 4 个 data 事件，总耗时 20.19 秒。本机仍缓存旧 DNS，因此报告明确记载连接 IP 覆盖，没有冒称本机默认 DNS 已刷新。

Nginx 主配置、原默认站点及当前 HTTPS 配置 SHA256 均未变，防火墙规则逐字未变。原有 HTTPS 地址、访问口令及无关服务保持。

本版本没有新增付费模型调用；真实模型在上一版本的验证结果仍属于上一版本，不能写成本版本已完成真实模型回归。新版本的引用恢复链由离线回放与状态恢复测试覆盖。

服务器证据：`/var/lib/zhiming-deployment/upgrade-afa6ffe/`（doctor.json、upgrade.json、源码归档和校验文件、旧发布记录）；当前版本为 `/etc/zhiming/release.json`。本机证据在 Git 忽略目录 `reports/server-upgrade-afa6ffe-20261029/`。原有证书正式续期网络限制、异地备份与 NTP 待办见 [运维说明](../deployment.md)。

## 需要回滚时

先确认没有后续版本或数据结构变更，选择维护窗口，在服务器执行：

```bash
test ! -e /opt/zhiming/failed-afa6ffe
test -d /opt/zhiming/rollback-2e93e41-20261029
systemctl stop zhiming
mv /opt/zhiming/app /opt/zhiming/failed-afa6ffe
mv /opt/zhiming/rollback-2e93e41-20261029 /opt/zhiming/app
cp -a /var/lib/zhiming-deployment/upgrade-afa6ffe/release-before.json /etc/zhiming/release.json
systemctl start zhiming
```

以上仅回退代码与版本记录，不覆盖业务库；回退后重新验证 HTTPS、排盘与历史。
