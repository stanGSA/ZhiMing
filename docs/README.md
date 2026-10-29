# 文档索引

## 设计与使用

- [设计与约定](design.md)：运行路径、知识库、多 Agent 编排、跨体系合并与审校、各插件的计算口径与验收方式
- [使用指南](usage.md)：网页版、朋友临时体验、命令行、接入真实模型、隐私与当前限制
- [服务器部署说明](deployment.md)：当前 Debian VPS 已部署状态、账号免费额度、注册限制、验证结果、HTTPS 待办与运维；含新旧服务器部署记录
- [项目计划书](占卜Agent项目计划书.md)：最初的范围、架构、知识库与评估设计
- [网页界面改版](web-ui-改版.md)

## 各阶段验收

| 阶段 | 内容 | 报告 |
| --- | --- | --- |
| 第一周 | harness、塔罗插件、知识库与工程门禁 | [验收报告](week1-验收报告.md) · [评审修复报告](week1-评审修复报告.md) · [材料](verification/README.md) |
| 第二、三周 | 西方占星（本命盘、行运）、八字 | [第二周](week2-验收报告.md) · [第三周](week3-验收报告.md) · [实施对应表](week23-实施对应表.md) · [缺陷分析](week1-3-缺陷分析.md) · [证据](verification/week23/README.md) |
| 第四周 | 多 Agent 编排 | [验收报告](week4-验收报告.md) · [真实模型测试](week4-真实模型测试.md) · [合并后状态恢复修复](week4-合并后状态恢复修复.md) |
| 第五周 | 跨体系合并、张力披露、宽松审校、画像复用 | [验收报告](week5-验收报告.md) · [合并后边界修复与真实模型测试](week5-合并后边界修复与真实模型测试.md) |
| 第六周 | 姓名五格、解梦、每日运势 | [验收报告](week6-验收报告.md) · [合并后五项修复](week6-合并后五项修复.md) |
| 阶段0 | 日历与时区、网页身份到期清理、危机确认与热线 | [验收](verification/stage0/README.md) · [复核修复](verification/stage0/review-fixes.md) |
| 阶段1 | 知识库双模型交叉审核 | [执行记录](verification/stage1/README.md) · [验收](verification/stage1/20261022-acceptance/report.md) · [运行目录](verification/kb-model-review/README.md) |
| 真实模型质量 | 后续独立验收任务 | [任务说明](verification/real-model-quality-task.md) |

## 评审整改

- [PR #1 整改清单](pr1-整改清单.md) · [整改验收](pr1-整改验收.md)
- [PR #7 合并后校验修复](pr7-合并后校验修复.md)
- [v2 截图整改验收](v2-截图整改验收.md)
- [网页界面验收](web-ui-验收.md)

## 回答风格调整

- [分层解读与表达层放宽](分层解读与表达层放宽.md) · [评审整改验收](分层解读-评审整改验收.md)
- [回答先表态与精简](回答先表态与精简.md)
- [回答说白话](回答说白话.md)

验收报告保留当时的测试与脚本名称；2026-10-23 之后的新位置见 [tests/README.md](../tests/README.md) 与 [scripts/archive/README.md](../scripts/archive/README.md)。`assets/` 存放 README 截图。
