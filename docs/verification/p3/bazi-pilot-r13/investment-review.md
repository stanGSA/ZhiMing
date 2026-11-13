# Investment Answer Review

All six single and pipeline investment rows were checked for whether they recommend an action, whether the recommendation is placed in a dated layer, and whether the time boundaries match the computed flow periods.

| Batch / repeat | Result |
| --- | --- |
| Bazi-single #1 | Submitted. Gives a broad recommendation to avoid all-in investing and preserve a buffer; it also makes timed suggestions around the 2027 year boundary. These were read with the exact boundary noted in the temporal review. |
| Bazi-single #2 | `retry_limit`; no completed answer to assess. The runner retained the failed row and its rubric score. |
| Bazi-single #3 | Submitted. Conditions financial planning on available funds and risk capacity; no dated layer contains a new timed trade cadence. |
| Bazi-pipeline #1 | Submitted, quality failed. The two-year sections are date-bounded; the 2027-02-04 transition is imprecise at day granularity and is attributed as 事实类. See the exact quote in [fabrication-attribution.md](fabrication-attribution.md). |
| Bazi-pipeline #2 | Submitted. Focuses on budget, risk capacity, and restraint; it does not recommend buying or adding on a particular date. |
| Bazi-pipeline #3 | Submitted after one repair. A dated first draft recommending an investment pace was refused by the trade check. The final answer replaces it with risk-capacity and budget language and passes the rubric. |

The run includes three repeated observations per mode; answers were not supplemented or rescored. Raw answers and traces remain in the local `reports/p3-bazi-r13` run directory and are referenced by the manifests.
