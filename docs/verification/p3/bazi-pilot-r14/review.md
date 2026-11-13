# P3 Bazi Pilot r14 Review

## Conclusion

The r14 campaign completed on merge commit `e9b8e9071315904561ecfdf00eacfc9595fee7f4`. Raw reports, source fingerprint, restored configuration, paired rows, and trace files are verified. **Do not freeze:** pipeline quality was 17/18, with one unsupported five-element strength inference. The original single baseline submitted 0/18. A separately documented single rerun submitted 13/18 but had only 4/10 scored submissions pass quality and is not paired with the pipeline run. See [assessment.md](assessment.md) and [the rerun record](../bazi-pilot-r14-single-retry/execution.md).

## Evidence scope

- [supplement-answers.md](supplement-answers.md) and [supplement-answers.json](supplement-answers.json): complete original outputs and score rows for all 36 requests, including incomplete single outcomes.
- [repair-evidence.json](repair-evidence.json) and [repair-quotes.json](repair-quotes.json): complete inspected drafts and original repair events.
- [execution.md](execution.md), [run-metadata.json](run-metadata.json), [integrity.json](integrity.json): run configuration, hashes, source commit and verification.
- [quality-reasons-with-answers.md](quality-reasons-with-answers.md), [fabrication-counts.md](fabrication-counts.md), [pipeline-problems-raw.md](pipeline-problems-raw.md): unchanged automated review, attribution counts and validator findings.
- [investment-review.md](investment-review.md), [temporal-manual-review.md](temporal-manual-review.md): focused answer-by-answer manual checks.
- [raw-manifest.json](raw-manifest.json), [trace-manifest.json](trace-manifest.json), [evidence-manifest.json](evidence-manifest.json): source integrity manifests.

The sample is six synthetic cases repeated three times, not 18 independent cases. The automated reviewer and writer used the same model family; this review preserves original scores and does not claim independent judge calibration. Relay fees were unavailable, so estimated cost is unknown.
