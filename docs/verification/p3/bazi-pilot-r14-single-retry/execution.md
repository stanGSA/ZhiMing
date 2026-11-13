# r14 Single Baseline Supplementary Rerun

This is a separate diagnostic rerun of the single arm after the original r14 baseline submitted 0/18. It does not replace the original run or form a same-batch pair with the original pipeline arm. Original r14 evidence and scores remain unchanged.

| Item | Value |
| --- | --- |
| Dataset | `evals/cases/bazi_pilot.yaml`, unchanged; 6 cases × 3 repeats |
| Mode / judge | `single` / `pro`, DeepSeek `deepseek-v4.1-flash` |
| Rubric | `v2-2026-10-24`, unchanged |
| Model/config/source fingerprint | Same model and experiment config as r14; source fingerprint `2a974a96ed903255910bca94169680c088fd71a74ac4f735ccff4aad4af60b68` |
| Config SHA256 | `3dfa2e81873c876568582d1b3138e802aa7e1d7c59dd60e03a52c94a87557d1b` |
| Run ID | `20261113T132243-496f969e` |
| Duration | 2026-11-13 13:22:43 UTC onward; exact finish timestamp is recorded in `attempt-metadata.json` |
| Model calls | 129 across 18 requests; maximum 12 per request |
| Raw report SHA256 | Recorded in `raw-manifest.json` |
| Personal config | Not modified; hash recorded in `attempt-metadata.json` |

## Result

All 18 requests completed as report rows: 13 submitted answers, 3 `ask_user`, and 2 `limit_reached`. Of the 13 submitted answers, 10 received a parsed judge result: 4 passed and 6 failed; 3 submitted answers were unscored. Only 3/13 submitted answers passed engineering checks. The remaining rows include repeated `_placeholder` argument-schema errors, invalid profile updates, missing or mismatched period calculations, and incomplete clarification flows.

The rerun recovers some scored single answers, but it is not a reliable comparative baseline: submission remained 13/18, most submissions failed engineering, and only 4/10 scored submissions passed quality. Since these are new stochastic requests made after the original pipeline batch, do not treat this as a paired result or replace the original r14 comparison. The report and all 18 traces preserve the raw outcomes; scores have not been edited.

## Files

- `live.json`: full original runner report for all 18 rows.
- `source-hashes.json`: source files observed by the runner.
- `traces/`: all 18 original trace files, indexed in `trace-manifest.json`.
- `attempt-metadata.json`, `raw-manifest.json`, `trace-manifest.json`, and `evidence-manifest.json`: execution provenance and integrity hashes.

The runner's `trace` fields in `live.json` retain their original local paths. Portable copies are included under `traces/`; use `trace-manifest.json` to map and verify them.
