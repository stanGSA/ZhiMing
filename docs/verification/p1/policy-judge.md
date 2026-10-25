# 表达策略判定对照

样本：135；模型：未调用。
regression assertions plus agent-authored labels; not human calibration

|方案|维度|TP|FP|FN|TN|precision|recall|
|---|---|---:|---:|---:|---:|---:|---:|
|regex|certainty|27|7|2|99|0.7941176470588235|0.9310344827586207|
|regex|discourage_care|18|4|1|112|0.8181818181818182|0.9473684210526315|

代理标注不等同人工校准；运行时默认保留严格正则。模型裁决失败时不放行。
