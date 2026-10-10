# AI 天气 Function Calling 助手

[![CI](https://github.com/eligiblex/ai-weather-function-calling/actions/workflows/ci.yml/badge.svg)](https://github.com/eligiblex/ai-weather-function-calling/actions/workflows/ci.yml)

用 Python 和智谱 GLM 实现一个可阅读、可测试的工具调用闭环：模型提出工具请求 → 应用校验参数并查询天气 → 工具结果回填 → 模型生成中文回答。

这是一个小型命令行练习项目，重点是工具协议与异常处理，而不是完整 Agent 平台。

## 已实现

- JSON Schema 定义天气工具；模型决定是否调用工具，一次回复可包含多个工具调用。
- JSON 解析 + 工具白名单 + 参数字段校验，不执行模型返回的代码。
- 每个工具结果保留 tool_call_id，与模型请求对应。
- 不支持的城市、HTTP 超时、错误状态和缺失字段转为可解释的工具错误。
- 密钥通过 .env / 环境变量管理；模型请求设超时及有限重试。
- 30 项离线测试覆盖两阶段调用、未知工具、恶意参数、无工具回答、输入校验及天气响应异常。

```text
用户问题 → GLM（tools schema） → tool_calls
                                 ↓
                         校验 JSON / 工具名 / 城市
                                 ↓
                           天气 HTTP 接口
                                 ↓
用户答案 ← GLM（二次生成） ← role=tool + tool_call_id
```

## 快速开始

建议 Python 3.11 / 3.12。需要自行申请有相应模型权限的智谱 API Key，模型调用可能计费。

```bash
git clone https://github.com/eligiblex/ai-weather-function-calling.git
cd ai-weather-function-calling
python -m venv .venv
```

Windows PowerShell：

```powershell
.\.venv\Scripts\Activate.ps1
Copy-Item .env.example .env
```

macOS / Linux：

```bash
source .venv/bin/activate
cp .env.example .env
```

编辑 .env 中的 ZHIPUAI_API_KEY 和 ZHIPUAI_MODEL，然后：

```bash
python -m pip install -r requirements.txt
python app.py "今天北京天气怎么样？"
python app.py "北京和昌平的天气分别如何？"
```

可用 --model 覆盖模型名。默认 glm-4；是否可用取决于你的账号和服务商当前支持范围。

## 数据与工具边界

- **当前仅内置北京、昌平两条城市编码**，见 city_codes.json。新增城市需先核对服务商编码，不宣称支持全国城市。
- 接口提供当天预报数据，输出带 forecast_date、data_time 和 source；不代表即时实测，也不保证数据新鲜度。
- 示例使用第三方公开天气接口 t.weather.itboy.net；当前代码使用 HTTP，没有传输加密或可用性 SLA，只用于练习，不传递身份或私密信息。
- 模型接收用户问题及工具返回数据。不要输入敏感信息。
- 工具结果回填后只做一次最终生成，不实现自动多轮规划、无限循环或自主执行任意工具。

## 测试

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m ruff check .
```

测试通过依赖注入模拟智谱 SDK 和天气响应，不消耗 API 额度。完整双外部服务调用需要你配置有效密钥后自行运行。详见 [验证记录](docs/validation.md)。

## 文件

- app.py：CLI 和工具调用编排。
- weather_tool.py：城市解析、天气 HTTP 请求、响应归一化、工具 Schema。
- city_codes.json：小型演示城市映射。
- tests/：流程、安全边界和故障测试。
- .github/workflows/ci.yml：离线持续集成。

## 安全与授权说明

不要提交 .env、真实密钥或含授权头的日志。曾泄露的密钥应在服务商控制台撤销，仅从代码删除不足以使旧密钥失效。

当前公开展示项目，尚未指定开源许可证。天气数据与模型服务遵循各自的使用条款。
