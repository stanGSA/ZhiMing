# name：体系汇总验收

负责人确认：按体系汇总全部初审及复审样本；通过率按当前内容哈希；kappa按全部真实及埋错样本的放行二分类计算，原三分类指标保留。阈值不变，保留所有失败样本；不是人工审核。

当前内容双审候选 219/220；质量校准达标：False；全部关口达标：False。

完整分子分母、每批原始失败指标和当前内容的证据来源见 [summary.json](summary.json)。

```json
{
  "detection": {
    "reviewer_a": 0.9487179487179487,
    "reviewer_b": 1.0
  },
  "detection_merged": 1.0,
  "rerun": {
    "reviewer_a": 0.8984375,
    "reviewer_b": 0.8802083333333334
  },
  "kappa": 0.3067,
  "kappa_real_three_class": 0.0198,
  "kappa_all_three_class": 0.2873,
  "observed_agreement": 0.7291666666666666,
  "observed_agreement_real_three_class": 0.7014492753623188,
  "pass_rate": 0.9954545454545455
}
```
