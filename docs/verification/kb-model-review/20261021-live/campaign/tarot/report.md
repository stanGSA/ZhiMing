# tarot：体系汇总验收

负责人确认：按体系汇总全部初审及复审样本；通过率按当前内容哈希；kappa按全部真实及埋错样本的放行二分类计算，原三分类指标保留。阈值不变，保留所有失败样本；不是人工审核。

当前内容双审候选 162/163；质量校准达标：True；全部关口达标：True。

完整分子分母、每批原始失败指标和当前内容的证据来源见 [summary.json](summary.json)。

```json
{
  "detection": {
    "reviewer_a": 0.8571428571428571,
    "reviewer_b": 0.9523809523809523
  },
  "detection_merged": 0.9523809523809523,
  "rerun": {
    "reviewer_a": 0.9141414141414141,
    "reviewer_b": 0.98989898989899
  },
  "kappa": 0.8836,
  "kappa_real_three_class": 0.7192,
  "kappa_all_three_class": 0.7069,
  "observed_agreement": 0.9747474747474747,
  "observed_agreement_real_three_class": 0.9830508474576272,
  "pass_rate": 0.9938650306748467
}
```
