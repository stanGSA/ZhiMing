# PR #1 整改清单

日期：2026-10-13。依据[复核修订的缺陷分析](week1-3-缺陷分析.md)，保留原PR与历史验收记录。本次只修改本地工作区，不自动合并PR或推送。

状态说明：“已修复”指实现和对应回归已验证，不等于所有模型回答或发布关口通过；“待审核/外部验证”不计为通过。首次7项回归失败XML及真实模型失败均保存在本地忽略目录。最终结果见[整改验收](pr1-整改验收.md)及[真实模型逐题记录](../reports/live-gpt-6.1-sol-pr1.md)。

| 项目 | 实施与验收要求 | 当前状态 |
|---|---|---|
| D1 中文日期 | `common/input_evidence.py`统一规范化中文日期与时刻，伪造时间继续拒绝 | 已修复；真实自然占星题及10次重复回答质量均通过 |
| D2 画像 | 性别规范枚举、出生日期规范化，旧“男/女”兼容读取，出生地跨会话复用；允许有证据的坐标与咨询时区；缓存考虑画像版本 | 已修复；真实测试另发现中文“时辰已知”画像遗漏，已补 |
| D3 海外八字 | 海外先确认真太阳时/固定UTC+8，保留历史口径，不擅自重写排盘 | 已修复，追问与确认后计算回归通过 |
| D4 事实约束 | 各插件负责领域校验；宫位支持标点/中文数字，未知时辰保护；行运引用绑定事件实体、日期、相位与容许度 | 已修复并真实复测；占星时机答复自动评审服务错误，仍未完成。不能宣称自然语言任意表述均可证明正确 |
| D5 信号契约 | horizon统一trait/timing/moment/psyche，兼容旧值；补全四主题键 | 已修复接口；relationship/finance是中性占位，倾向细分仍待人工内容审核 |
| D6 行运语义 | 明确orb是精确事件的解释容许度，精确时刻残差近零不代表本命强度无效 | 文档澄清；入相/出相持续窗口是独立增强项，本次尚未实现，不冒充修复完成 |
| D7 区间时区 | 区分出生时区与consultation_tz；海外缺依据先追问，可保存复用 | 已修复，防止模型擅填北京时间 |
| D8 知识文案 | 改写机械拼接语病，条目版本升至3，旧知识快照保留 | 已改进；覆盖100%，人工审核仍0%，职业例子模板性需人审 |
| D9 作答完整性 | 去除“下个月跳槽”专用规则，按timing问题检查直接倾向；扩充起运问法 | 已改进；通用语义质量仍由单独评审及人工抽查补充 |
| D10 日期范围 | 只识别连接的区间，中文年月与相对月份规范化；限定当前reading原话 | 已修复，旧问题/生日后置/中文月份/相对月份回归通过 |
| D11 测试输入 | 增加6题自然中文与跨会话题，不在问题中提示预期行为 | 已加入真实测试脚本 |
| D12 批次证据 | 每批保存源文件哈希，最终代码完整批次与针对性复测分开统计 | 已落实；完整批次12/20→17/20；重复测试严格8/10、质量10/10；另三题复测严格1/3，不拼接通过率 |
| D13 评审独立性 | 每题四项质量rubric单独评估，再核对问答与计算 | 同模型评审不是独立人审；20条人工校准仍待人工，不虚报 |
| D14 八字金标独立性 | 原50例/57变体继续严格回归，保留同源字段局限 | 数值回归通过；权威万年历独立抽查仍待完成，不改参考答案 |
| D15 CI及快照 | workflow缓存+下载+校验，再doctor；GeoNames用固定版本发布归档替代每日变动地址 | 已修复本地配置；新远程CI运行需提交后验证，当前未推送 |
| D16 原生路径 | 去掉os.chdir/relpath，Windows短路径或ASCII内容寻址缓存 | 已修复；禁止chdir/relpath的实际排盘回归通过 |
| D17 模型适配 | 非法工具JSON转为可恢复invalid_arguments；usage缺失暂停该轮，不记作零预算 | 已修复，恢复/终止测试通过；前三周仍串行 |
| D18 消耗 | 移除历史读取中重复signals传输，记录实际usage/延迟/请求次数 | 已优化；最终整批104次对话响应、19次评审响应，输入612218/输出29149 token；失败请求无usage不推算，不承诺未来多Agent预算 |
| D19 文档 | 旧9/9就地标明撤回、14题混合批次与本地链接说明、旧未推送状态加时间注记 | 已修订，原失败问答保留 |
| D20 插件边界 | 输出校验通过插件validate_output注册，公共层不再导入占星常量或塔罗牌目录 | 已修复接口，三插件协议测试通过 |

## 本地证据与复现

原始数据、测试数据库、trace留在`reports/pr1-remediation/`及`data/`，均不入Git。地名数据来自GeoNames（CC BY 4.0），使用PyPI发布的geonamescache 3.0.2归档中cities15000 JSON，归档代码不安装、不执行；URL、版本和SHA256见`scripts/data_manifest.yaml`。旧GeoNames快照继续本地保留。

```powershell
uv sync --locked --extra llm
uv run python -m scripts.fetch_data
uv run python -m knowledge.build
uv run python -m scripts.doctor
uv run pytest -q --junitxml=reports/pr1-remediation/reproduced-tests.xml
uv run python -m scripts.verify_week23 --output reports/pr1-remediation/computations.json
uv run python -m evals.run --suite trajectory --output reports/pr1-remediation/evals
uv run python -m scripts.check_model
uv run python -m scripts.live_week23 --natural --output reports/pr1-remediation/live
uv run python -m scripts.live_pr1
```

默认真实测试为原14题加6题自然输入，共20题。请求模型固定gpt-6.1-sol；返回模型名与usage如实记录，不能证明第三方底层模型身份。缺失usage和未执行检查单独标记，不能以HTTP成功或工具成功替代回答质量。

最终确定性回归216通过、0失败、0跳过；占星11/11、八字50例57变体通过。最后完整真实批次的三个未通过项为：占星时机误读历史并发生评审服务错误、投资题首评存在争议、海外题合成补充资料不完整而继续追问。补全海外资料后回答质量通过，但仍有一次画像工具拒绝；所有首次失败保留。新远程CI、独立人工校准及内容审核尚未完成。
