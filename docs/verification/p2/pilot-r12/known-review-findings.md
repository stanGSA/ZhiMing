# r12 被测代码中的已知规则问题

被测 PR #53 提交 `e1314b42cf029b01bb03a662d3d58a24ca765b87`。以下为实验前代码审查和离线脚本模型对照，不并入108条线上结果。

1. `plugins/dream/validation.py:274–277`：“这个梦不可能完全没有预示现实中的好转”“这个梦不是完全没有预示现实中的好转”仍0修复提交；基线拒绝并要求改写。程度词“完全”隔断外层否定检测。
2. `plugins/dream/validation.py:52–53`：“这个梦不是不幸的预兆”“这个梦不是不祥的预兆”被误拒；两稿保留该句时触发keywords降级，基线直接通过。禁用否定字符误伤完整形容词。

完整流水线对照见 [known-boundary-integration.json](known-boundary-integration.json)，最小谓词回放见 [validation-diagnostics.json](validation-diagnostics.json)。本轮没有修改这些规则；pilot未触发全部反例也不能消除已复现缺陷。
