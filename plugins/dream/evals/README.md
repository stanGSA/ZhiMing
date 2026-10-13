解梦意象用例唯一来源为 `evals/cases/dream_annotations.yaml`（100条），不复制或改写金标。

执行 `python -m pytest tests/test_week6.py -k dream` 与 `python -m evals.run --suite week6`。

离线评估使用词典扫描基线（不经LLM），只验证知识库覆盖、同义词与未命中处理；计划中的准确率≥0.85、召回率≥0.8针对真实模型抽取意象，需另行运行。
