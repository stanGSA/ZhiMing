# r22 预检

沿用工作区 config.yaml 的 deepseek-flash，凭据来自原项目 D:\知命\.env，接口为 https://api.deepseek.com。本轮未读取或使用桌面 key.txt；配置文件未改写。

普通回复、工具调用、pro评委三项探针全部通过，输出分别为1、21、1 token，低于普通回复3、工具40的上限；工具探针实际返回 get_profile。请求及返回模型字段均为 deepseek-flash。thinking配置为disabled；服务未提供reasoning_tokens计数，null不解释为零。详见 service-probe.json。
