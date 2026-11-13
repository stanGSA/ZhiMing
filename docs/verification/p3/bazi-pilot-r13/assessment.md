# P3 Bazi Pilot r13 Assessment

The four P1 operating criteria passed. The stricter B freeze criterion did not pass because manual attribution found one checkable date-boundary error in a submitted pipeline answer.

| Measure | Bazi-single | Bazi-pipeline |
| --- | ---: | ---: |
| Completed tasks | 12/18 | 18/18 |
| Submitted answers | 12/18 | 18/18 |
| Scored answers | 18/18 | 18/18 |
| Submitted-answer quality | 9/12 (75.0%) | 16/18 (88.9%) |
| No tool errors | 5/18 | 18/18 |
| Maximum model calls per answer | 11 | 2 |
| Repairs / degradations | 0 / 0 | 4 / 1 |
| Median / P95 latency | 34.0 / 52.6 s | 8.9 / 16.8 s |
| Mean runtime input / output tokens | 45,247 / 2,738 | 6,066 / 859 |
| Estimated cost | Unknown | Unknown |

P1 criteria: all pipeline answers submitted (18/18); no pipeline tool, step, or budget failures; maximum two model calls, below the limit of three; and submitted-answer quality higher than the same-batch single baseline (16/18 versus 9/12). Paired task-and-quality results were 9 pipeline wins, 2 single wins, and 7 ties across 18 repeated pairs.

The pipeline rubric failures were `no_fabricated_facts` on investment #1 and typed-birth #2, plus one `time_consistent` failure. Offline attribution classified investment #1 as a factual boundary-precision issue and typed-birth #2 as narrative overreach. The single baseline had three `no_fabricated_facts` failures, all attributed to narrative claims under the stated review convention. These are six repeated measurements of each of six cases, not 18 independent cases. The runner and judge used the same DeepSeek model; automated review has not been independently calibrated by a human.

The r13 fixes behaved as intended in the checked outputs: the career answers using ordinary “配合” language were not rejected as a 合 relation; the pipeline dayun #3 answer placed 2026 in the current cycle's first half; and an over-specific timed investment draft was refused and revised. One pipeline dayun answer still degraded after it named the wrong preceding cycle; this was a genuine answer error, not an r13 false rejection.

**B is not met; do not freeze.** The investment #1 date-only wording labels all of 2027-02-04 as before/at 立春, while the computed boundary is 2027-02-04 09:46 Beijing time. The original scores are unchanged. See [investment-review.md](investment-review.md), [temporal-manual-review.md](temporal-manual-review.md), and [acceptance.json](acceptance.json).
