# 充值后在项目根目录续跑同一个第三轮；只补daily的两次reviewer_a.p2，其他输出缓存复用。
$env:PYTHONUTF8 = "1"
.venv/Scripts/python.exe -m scripts.kb_review_live pilot --run-root docs/verification/kb-model-review/stage1-r3 --calibration docs/verification/kb-model-review/stage1-r3/calibration.yaml --iteration 3 --concurrency 4

# 仅当六体系全部met:true才允许预登记；预登记必须提交推送后再正式调用。
