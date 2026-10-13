姓名笔画规范用例唯一来源为 `evals/cases/name_strokes.yaml`（200字），不复制或改写参考值。

执行 `python -m pytest tests/test_week6.py -k "strokes or grids or name"` 与 `python -m evals.run --suite week6`。

验收包括200字默认写法与康熙笔画、37个公认姓氏、19个待定稿字的处理策略（见 `scripts/review_week6_datasets.py`）、五格公式手算样例、复姓拆分、查不到的字追问而不猜测。
