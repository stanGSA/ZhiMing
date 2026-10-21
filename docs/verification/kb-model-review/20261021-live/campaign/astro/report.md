# astro：体系汇总验收

负责人确认：按体系汇总全部初审及复审样本；通过率按当前内容哈希；kappa按全部真实及埋错样本的放行二分类计算，原三分类指标保留。阈值不变，保留所有失败样本；不是人工审核。

当前内容双审候选 280/280；质量校准达标：True；全部关口达标：True。

完整分子分母、每批原始失败指标和当前内容的证据来源见 [summary.json](summary.json)。

```json
{
  "detection": {
    "reviewer_a": 1.0,
    "reviewer_b": 1.0
  },
  "detection_merged": 1.0,
  "rerun": {
    "reviewer_a": 0.9556213017751479,
    "reviewer_b": 1.0
  },
  "kappa": 0.8336,
  "kappa_real_three_class": -0.0151,
  "kappa_all_three_class": 0.7716,
  "observed_agreement": 0.9644970414201184,
  "observed_agreement_real_three_class": 0.9603960396039604,
  "pass_rate": 1.0
}
```
