# P3 Bazi Pilot r14 Assessment

## Conclusion

The experiment ran against merge commit `e9b8e9071315904561ecfdf00eacfc9595fee7f4`. Its source fingerprint, unchanged experiment configuration, restored personal configuration, 36 raw rows, and trace files are verified in [integrity.json](integrity.json). Original answers and judge scores are preserved.

**Do not freeze.** The pipeline submitted 18/18 and passed quality on 17/18 (94.4%); one overseas-birth answer failed `supported_conclusion` because it inferred “火偏旺” from element counts. The original same-batch single baseline submitted 0/18, so that batch cannot establish an answer-quality comparison. A later, separate single rerun submitted 13/18; of 10 scored submissions, 4 passed and 6 failed, while 3 were unscored. This adds descriptive evidence but cannot be treated as a paired comparison with the original pipeline run. Neither group has a submitted `no_fabricated_facts=false` result in the original r14 batch; the single denominator is zero, not evidence of zero fabrication risk. The pipeline rate is descriptive, not an independent quality estimate.

| Measure | Bazi-single | Bazi-pipeline |
| --- | ---: | ---: |
| Completed tasks / submitted answers | 0/18 | 18/18 |
| Scored / unscored | 10/18 / 8/18 | 18/18 / 0/18 |
| Submitted-answer quality | Not applicable (0 submitted) | 17/18 (94.4%) |
| Maximum model calls | 12 | 2 |
| Tool errors | 8 | 1 |
| Repairs / degradations | 0 / 0 | 4 / 0 |
| No-fabrication failures on submitted answers | 0/0 | 0/18 |

## Interpretation

The pipeline met submission completion and the three-call ceiling, but the single run collapsed: 11 rows returned ordinary text instead of a clarification, six reached a step or budget limit, and one ended in a model error. Five rows had a `get_profile` parameter-schema error; the other tool errors include unconfirmed birth location and a boolean schema error. These outcomes prevent the same-batch quality criterion from being assessed.

The sole pipeline rubric failure is on overseas solar #1. Its response says the natal count “火偏旺” and describes “火旺之地” despite explicitly reporting 火4、金水0; the count is accurate, but the strength inference is not justified by a simple count. It also attributes urgency and implementation style to that count. See [quality-reasons-with-answers.md](quality-reasons-with-answers.md) and the original result in [supplement-answers.md](supplement-answers.md). No score was changed.

Focused manual review found no actionable factual escape in the three investment answers, the timed advice within them, or the three dayun answers. The flow-month boundary statements reviewed across career, overseas, typed-birth, and investment responses agree with the computed timestamps; range phrasing is documented in [temporal-manual-review.md](temporal-manual-review.md). This limited review does not substitute for independent calibration of the automated judge. The writer and judge used the same model family; relay pricing was unavailable, so cost remains unknown.

## Evidence

- All 36 original final outputs, raw score rows, repair evidence, execution details, and integrity manifests are linked from [review.md](review.md).
- All runs share the same 183-file source fingerprint. The personally customized `config.yaml` was restored byte-for-byte after the experiment.
- Deterministic r14 regression tests: 35 passed in an isolated worktree at the measured commit. Running them in the main checkout uses the user-local config, which selects tarot only and causes Bazi-specific fixtures to return `model_error`; no model experiment was rerun to diagnose this.
- The separate single rerun and its complete report and traces are documented in [r14 single rerun](../bazi-pilot-r14-single-retry/execution.md). It used the same model, config, dataset, and rubric, but ran later as a new set of stochastic requests; it does not replace the original rows or create same-batch pairs.
