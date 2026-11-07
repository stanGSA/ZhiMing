# 留出集按新旧两种 direct_timing_answer 口径重评

旧口径：P1、P2 期间的断言，只认“下个月……适合……跳槽”一种语序。新口径：P3.0，两种语序都认（`evals/heldout.py`）。其余断言不变，未调用模型。

| 批次 | 原始 SHA256 | 题数 | 旧口径通过 | 新口径通过 | 跳槽题 旧 / 新 | 摘要首句 |
| --- | --- | ---: | ---: | ---: | --- | --- |
| D:\知命\reports\p1\codego-v4\B0-heldout\a2e58e5113f5\live.json | `0dc79fd95ff656b5` | 17 | 14/17 | 14/17 | 通过 / 通过 | 下个月适合跳槽，更准确地说，适合带着条件走 |
| D:\知命\reports\p1\codego-v4\Final-heldout\cee7982ed861\live.json | `4b09ac632a86ca32` | 17 | 16/17 | 16/17 | 通过 / 通过 | 下个月适合跳槽，但只有一个前提：先拿到书面offer再提离职 |
| D:\知命\reports\p1-tarot\Tarot-heldout-pipeline\231b77e810a5\live.json | `a80a9b673952f03d` | 17 | 16/17 | 17/17 | 失败 / 通过 | 下个月跳槽有条件适合：先补齐信息再行动，别带着猜测递辞呈 |
| D:\知命\reports\p1-tarot-r2\Tarot-heldout-pipeline\63681750b422\live.json | `179d1630b4924849` | 17 | 16/17 | 17/17 | 失败 / 通过 | 下个月跳槽有条件适合，前提是把过去的边界和评判问题处理好，并先理顺当下多方竞争的摩擦 |
