# 回答校验与知识库校验同步

## 问题与修复

Windows CI 在 `test_shared_chat_secure_cookie_origins_and_separate_browsers` 随机抽牌后返回空 reading。156种牌面探测定位到宝剑九逆位（seed 75）、权杖十逆位（seed 162）：已审核源释义中的“不代表状态必然好转或事件必然发生”“不代表负担必然减轻”被回答校验误判为肯定断言，最终达到步数上限。

原知识库检查已接受这些受限否定句。本次把同一份列举主体、谓语的规则移到 `common/output_policy.py`，回答和知识库统一使用。未扩大成任意含“不”的句子豁免；转折后、并列但不受否定支配的肯定断言仍被拦截。

用户已在本会话明确批准实施修复和回归测试。CI排查使用 `gh-fix-ci` 技能；本机没有gh，通过已有Git凭据管理器和GitHub API读取检查，密钥不进入日志。

## 验证

- 相关回归80项通过（31.53秒），包括两seed完整runtime生成reading、受限否定句以及转折/并列后的肯定断言拦截，见 `tests-ci-fix-targeted.txt`。
- 新增测试最初两次误用返回字段（`id`、嵌套`reading_id`），失败日志保留为 `tests-ci-fix-targeted-first.txt`、`tests-ci-fix-targeted-second.txt`；两次均为测试字段错误，runtime已提交reading。
- 离线demo runtime遍历全部156种塔罗牌面，156/156提交reading，见 `tarot-156-after-ci-fix.json`。只使用独立临时数据库和合成用户，不能等同于真实模型回答质量验收。
- 全部1171条源内容在修复前后产生相同17条代码检查发现；知识库版本保持 `v1-984b14f53d4d43c7`，见 `ci-fix-source-check.json`。不改变任何源内容批准。
- 原提交 `037ca29` 的Windows失败日志保留；后续提交 `da2c90c` 的Ubuntu/Windows检查均通过，见 `ci-da2c90c.json`。随机测试曾成功不能替代对两种失败牌面的明确回归。

完整回归853项通过（650.14秒），见 `tests-full-ci-fix.txt`；Ruff、153文件格式检查、doctor通过（`doctor-ci-fix.txt`）。本次修复提交的CI结果以本目录后续记录为准。R2开发集试跑与阶段1知识库验收分开记录，本修复不代表知识库验收通过。
