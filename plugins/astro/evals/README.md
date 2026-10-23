占星规范用例唯一来源为 `evals/cases/reference_charts.yaml`（11盘），不复制或改写参考值。

执行 `python -m pytest tests/plugins/test_astro_bazi_calculations.py -k 'reference_charts or skyfield or transits'`，以及 `python -m scripts.archive.verify_week23`。

本命盘验收包括位置、落座、速度、逆行、宫位、四轴、相位、高纬度回退和时间未知；Skyfield/JPL以相同TT、地心视位置、日期黄道独立计算，不以Swiss库自检代替。
