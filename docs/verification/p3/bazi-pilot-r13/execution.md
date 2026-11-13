# P3 Bazi Pilot r13 Execution

| Item | Value |
| --- | --- |
| Run date | 2026-11-12 UTC / 2026-11-13 Asia/Shanghai |
| Source branch | `claude_modify_model` |
| Source commit | `c49056cc7ef43c4f2d3bee228e5eaa2f9e7a312a` (merge of PR #72; head `3fe979ba835c6ded5bdbde618e9e7b5866071dbf`) |
| Source fingerprint | `a6cd1a6ecd0d3e992cc0e359d890fd14bbc9c405ecf9fc1a63d16cee444c7de8` |
| Sampled source files | 183; 182 non-config files match the source commit |
| Experiment config | `3dfa2e81...`; `reports/p3-bazi-r9/config.experiment.yaml` |
| Personal config before/after | `d20f8ebd922f11bad6cda4b850ac66d17fcb50d0a656dd7800e89671cf243a24` |
| Pricing file | `d6d6cb2c2c385d894d79cb6c054a330f79458e068ef6183744f58ea65c812ef6`; byte-identical to r12 |
| Runtime / judge model | requested and returned: `deepseek-v4.1-flash` |
| Rubric | `v2-2026-10-24`; judge role `pro` |
| Judge options | `thinking=disabled`, `max_tokens=8192`, no `reasoning_effort` |
| Cases | 6 Bazi cases × 3 repeats = 18 rows per mode |

The campaign ran on the merged r13 source with the agreed experiment configuration. It started at 2026-11-12 17:46:10 UTC and finished at 18:03:24 UTC. `Bazi-single` ran from 17:46:10 to 17:58:32; `Bazi-pipeline` ran from 17:58:32 to 18:03:24. Both runner commands returned 1 because the batch contains failed task or quality outcomes; both produced complete 18-row reports and the campaign continued through both modes.

The commands followed review §7:

```powershell
.venv\Scripts\python.exe -X utf8 -m scripts.p1_campaign --campaign p3-bazi --root reports/p3-bazi-r13 --snapshot . --baseline . --publish docs/verification/p3/bazi-pilot-r13
.venv\Scripts\python.exe -X utf8 -m scripts.quality_reasons reports/p3-bazi-r13/Bazi-single reports/p3-bazi-r13/Bazi-pipeline --answers --output reports/p3-bazi-r13/quality-reasons.md
.venv\Scripts\python.exe -X utf8 -m scripts.quality_reasons reports/p3-bazi-r13/Bazi-single reports/p3-bazi-r13/Bazi-pipeline --counts-only --reviewed reports/p3-bazi-r13/fabrication-reviewed.yaml --output docs/verification/p3/bazi-pilot-r13/fabrication-counts.md
.venv\Scripts\python.exe -X utf8 -m scripts.pipeline_problems reports/p3-bazi-r13/Bazi-pipeline --output docs/verification/p3/bazi-pilot-r13/pipeline-problems-raw.md
```

The required offline attribution file was created after inspecting every scored `no_fabricated_facts` failure. The counts command was first attempted before that file existed and stopped with `FileNotFoundError`; it was then run successfully with the completed file. The raw pipeline-problem report was also generated successfully. The personal `config.yaml` was restored in a `finally` block and its original SHA256 was verified. Pricing rates are unavailable for the configured relay, so cost is unknown, not zero.

## Published Run Files

- [Bazi-single-summary.json](Bazi-single-summary.json), [Bazi-pipeline-summary.json](Bazi-pipeline-summary.json)
- [Bazi-single-source-hashes.json](Bazi-single-source-hashes.json), [Bazi-pipeline-source-hashes.json](Bazi-pipeline-source-hashes.json)
- [raw-manifest.json](raw-manifest.json), [trace-manifest.json](trace-manifest.json), [evidence-manifest.json](evidence-manifest.json)
- [quality-reasons-with-answers.md](quality-reasons-with-answers.md), [fabrication-counts.md](fabrication-counts.md), [pipeline-problems-raw.md](pipeline-problems-raw.md)

Before Git publication, generated text files were normalized to LF and Markdown trailing spaces were removed. The evidence manifest was regenerated from the publication bytes; local raw reports and traces were unchanged.
