每日运势没有外部金标：它在代码中组合占星、八字与塔罗，验收看可复现性。

执行 `python -m pytest tests/plugins/test_name_dream_daily.py -k daily` 与 `python -m evals.run --suite week6`：同一用户同一天跨会话调用10次结果逐字节一致（读 `daily` 缓存）、纯函数重算与缓存一致、同 seed 抽牌100次一致、不同日期种子不同、出生资料变化后重新计算。
