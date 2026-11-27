# 文档索引

## 设计与使用

- [设计与约定](design.md)：运行路径、知识库、多 Agent 编排、跨体系合并与审校、各插件的计算口径与验收方式
- [使用指南](usage.md)：网页版、朋友临时体验、命令行、接入真实模型、MCP server、隐私与当前限制

> 以下历史计划、阶段验收、PR 评审与风格迭代记录已归档至 [`archive/`](archive/)，结构化验证证据保留在 [`verification/`](verification/)。

## 历史计划与界面设计

- [项目计划书](archive/占卜Agent项目计划书.md)：最初的范围、架构、知识库与评估设计
- [项目完善计划书](archive/项目完善计划书.md)：阶段 0–1 的工程与知识库完善计划
- [网页界面改版](archive/web-ui-改版.md)

## 各阶段验收

| 阶段 | 内容 | 报告 |
| --- | --- | --- |
| 第一周 | harness、塔罗插件、知识库与工程门禁 | [验收报告](archive/week1-验收报告.md) · [评审修复报告](archive/week1-评审修复报告.md) · [材料](verification/README.md) |
| 第二、三周 | 西方占星（本命盘、行运）、八字 | [第二周](archive/week2-验收报告.md) · [第三周](archive/week3-验收报告.md) · [实施对应表](archive/week23-实施对应表.md) · [缺陷分析](archive/week1-3-缺陷分析.md) · [证据](verification/week23/README.md) |
| 第四周 | 多 Agent 编排 | [验收报告](archive/week4-验收报告.md) · [真实模型测试](archive/week4-真实模型测试.md) · [合并后状态恢复修复](archive/week4-合并后状态恢复修复.md) |
| 第五周 | 跨体系合并、张力披露、宽松审校、画像复用 | [验收报告](archive/week5-验收报告.md) · [合并后边界修复与真实模型测试](archive/week5-合并后边界修复与真实模型测试.md) |
| 第六周 | 姓名五格、解梦、每日运势 | [验收报告](archive/week6-验收报告.md) · [合并后五项修复](archive/week6-合并后五项修复.md) |
| 阶段0 | 日历与时区、网页身份到期清理、危机确认与热线 | [验收](verification/stage0/README.md) · [复核修复](verification/stage0/review-fixes.md) |
| 阶段1 | 知识库双模型交叉审核 | [执行记录](verification/stage1/README.md) · [验收](verification/stage1/20261022-acceptance/report.md) · [运行目录](verification/kb-model-review/README.md) |
| 真实模型质量 | 后续独立验收任务 | [任务说明](verification/real-model-quality-task.md) |

## 评审整改

- [PR #1 整改清单](archive/pr1-整改清单.md) · [整改验收](archive/pr1-整改验收.md)
- [PR #7 合并后校验修复](archive/pr7-合并后校验修复.md)
- [v2 截图整改验收](archive/v2-截图整改验收.md)
- [网页界面验收](archive/web-ui-验收.md)

## 回答风格调整

- [分层解读与表达层放宽](archive/分层解读与表达层放宽.md) · [评审整改验收](archive/分层解读-评审整改验收.md)
- [回答先表态与精简](archive/回答先表态与精简.md)
- [回答说白话](archive/回答说白话.md)

验收报告保留当时的测试与脚本名称；2026-10-23 之后的新位置见 [tests/README.md](../tests/README.md) 与 [scripts/archive/README.md](../scripts/archive/README.md)。`assets/` 存放 README 截图。
