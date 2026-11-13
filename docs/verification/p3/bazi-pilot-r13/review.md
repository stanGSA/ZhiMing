# P3 Bazi Pilot r13 Review

## Conclusion

The post-merge r13 experiment completed and its source, configuration, raw reports, traces, and score rows were checked. All four P1 operating criteria passed: the pipeline submitted 18/18, had no tool or budget failures, used at most two calls per answer, and reached 16/18 submitted-answer quality versus 9/12 for single.

**B is not met; do not freeze.** One pipeline investment answer has an imprecise date-only 立春 boundary on 2027-02-04. The automated judge also found two no-fabrication failures in the pipeline; offline review classified one as factual and one as narrative. Original judge scores were preserved. See [assessment.md](assessment.md), [acceptance.json](acceptance.json), and [fabrication-attribution.md](fabrication-attribution.md).

## Evidence

- Run and configuration provenance: [execution.md](execution.md), [run-metadata.json](run-metadata.json), [integrity.json](integrity.json).
- Raw run summaries and source hashes: [Bazi-single-summary.json](Bazi-single-summary.json), [Bazi-pipeline-summary.json](Bazi-pipeline-summary.json), [Bazi-single-source-hashes.json](Bazi-single-source-hashes.json), [Bazi-pipeline-source-hashes.json](Bazi-pipeline-source-hashes.json).
- Answer-level rubric reasons, counts, and validator issues: [quality-reasons-with-answers.md](quality-reasons-with-answers.md), [fabrication-counts.md](fabrication-counts.md), [pipeline-problems-raw.md](pipeline-problems-raw.md).
- Focused reviews: [investment-review.md](investment-review.md), [temporal-manual-review.md](temporal-manual-review.md).
- Integrity manifests: [raw-manifest.json](raw-manifest.json), [trace-manifest.json](trace-manifest.json), [evidence-manifest.json](evidence-manifest.json).

There were six distinct synthetic cases, each repeated three times. The same model family served as both writer and judge, so the quality score is descriptive, not independent calibration. Relay rates were unavailable; cost is unknown. The published summaries retain all failed, unscored, ask-user, and retry-limit outcomes without补评.
