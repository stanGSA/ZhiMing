# P1 提示词审计

日期：2026-10-24。对照实施手册附录 A 与 `p1-b0` 的旧提示词。

|规则|最终位置|代码保证与保留理由|
|---|---|---|
|新疆钟表时区|`plugins/context.py:birth_values`|返回 confirm_clock_timezone；仍逐项核对用户原话|
|真太阳时/起运口径|`common/domain_rules.py` 八字模块、八字工具字段|保留传统算法约定；physical 仍要求明确原话|
|地点候选与真实编号|`plugins/context.py:location_choices`、`common/location.py`|唯一已确认地点自动填参，错误返回候选编号；歧义仍追问|
|start/spread 参数|`StartInput`、塔罗输入和校验器|structured systems/requested_spread；多余字段继续禁止|
|出生钟表与默认历法|八字模块、`plugins/bazi/tools.py`|来自原话或画像，农历闰月须确认|
|画像 evidence、consultation_tz、prefs_json|update_profile 工具描述、原校验器|不凭空写入资料；咨询时区与出生时区分开|
|回答日主/起运/首运|八字模块和可渲染事实附录|回答要求仍提醒模型，facts 来自计算|
|职业工作方式|占星模块和全局表达规则|具体岗位只是待现实验证的例子|
|流程与依赖|`common/stages.py`、Guard|阶段过滤 schemas；Guard 权限/来源/依赖继续校验|
|时机计算|`common/facts.py`、专家 report 校验器|无行运/流期不得用原局代替|
|完整 ref_id 抄写|`harness/refs.py`、loop/guard 边界|模型看 Rn，持久化和事实校验用全名；跨轮不重新分配别名|
|塔罗顺序、牌阵定义|塔罗模块、draw_tarot 字段和 dependency|先 start 再抽；requested_spread 缺省由代码填|
|追问不重抽|全局短规则、followup 阶段|正在处理追问仅 read/lookup/submit；追问结束后新问题可 start|
|姓名|姓名模块、analyze_name 描述和校验器|来源/复姓/歧义写法硬校验保持|
|解梦|解梦模块、lookup_dream_symbols 描述|原文 phrase 与 hits 来源校验保持|
|每日运势|daily 模块和工具描述|一次组合调用，日期来自会话日历；幸运色是传统约定|
|闲聊/高风险/危机|全局规则和应用安全流程|保留；不以阶段工具过滤替代安全机制|

固定 system 前缀保持稳定，体系细则在 start_reading 结果里按 systems 返回；未明确选择时返回六体系细则，不猜测用户选择。阶段门控会改变工具 schema 前缀，缓存效果必须从 B0/最终版实测，不能仅由提示词字符数推断。

本机读取：single system 1523字符（旧版5445），multi system 1698字符；字符数不是 tokenizer token 数。未采用 `json.loads(strict=False)`：阶段0与 B0-single trace 仅发现逗号/冒号错误，没有控制字符错误证据。
