八字规范用例唯一来源为 `evals/cases/bazi_boundary.yaml`（50例），不复制或改写参考值。

执行 `python -m pytest tests/test_week23_calculations.py -k 'bazi or period or solar or gap or fold'`，以及 `python -m scripts.verify_week23`。

所有原始边界逐项执行；两种子时结果分别比较；需要追问的三例按行为验收。农历例先验证未确认时必须追问，再使用用例中明确的历法/闰月资料转换，不借用给定公历日期绕过转换。
