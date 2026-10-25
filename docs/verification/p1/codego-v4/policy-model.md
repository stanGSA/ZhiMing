# 表达策略判定对照

样本：135；模型：deepseek-v4-flash。
regression assertions plus agent-authored labels; not human calibration

|方案|维度|TP|FP|FN|TN|precision|recall|
|---|---|---:|---:|---:|---:|---:|---:|
|regex|certainty|27|7|2|99|0.7941176470588235|0.9310344827586207|
|regex|discourage_care|18|4|1|112|0.8181818181818182|0.9473684210526315|
|model_only|certainty|26|10|3|96|0.7222222222222222|0.896551724137931|
|model_only|discourage_care|15|0|4|116|1.0|0.7894736842105263|
|regex_then_model|certainty|26|0|3|106|1.0|0.896551724137931|
|regex_then_model|discourage_care|15|0|4|116|1.0|0.7894736842105263|

代理标注不等同人工校准；运行时默认保留严格正则。模型裁决失败时不放行。
