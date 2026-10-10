"""Command-line weather assistant powered by GLM function calling."""

from __future__ import annotations

import argparse
import json
import os
import sys

from pathlib import Path

from dotenv import load_dotenv
from zhipuai import ZhipuAI

from weather_tool import AVAILABLE_FUNCTIONS, TOOLS, ForecastDateError, WeatherLookupError, beijing_today


SYSTEM_PROMPT = (
    "你是天气查询助手。涉及实时天气时必须调用工具；"
    "工具没有返回的信息不要猜测，并用简洁中文回答。"
    "工具仅支持北京时间当天预报，不支持其他日期；请在回答中明确写出 forecast_date。"
    "统一使用具体年月日，不使用今天、明天等相对日期，以免回答期间跨日产生歧义。"
    "data_time 是接口更新时间，不能当作预报日期。预报不是实时实测，不能宣称实时观测。"
    "工具返回错误时明确说明，不能编造天气或把旧数据称为今天。"
)


def build_client() -> ZhipuAI:
    load_dotenv(Path(__file__).with_name('.env'))
    api_key = os.getenv("ZHIPUAI_API_KEY") or os.getenv("ZHIPU_API_KEY")
    if not api_key:
        raise RuntimeError("请先在 .env 中配置 ZHIPUAI_API_KEY")
    return ZhipuAI(api_key=api_key, timeout=30, max_retries=1)


def ask_weather(question: str, model: str | None = None, *, client=None) -> str:
    load_dotenv(Path(__file__).with_name('.env'))
    if not isinstance(question, str) or not question.strip() or len(question) > 1000:
        raise ValueError("问题需为 1 至 1000 字的非空文本")
    client = client if client is not None else build_client()
    model = model or os.getenv('ZHIPUAI_MODEL', 'glm-4')
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT + f' 当前北京时间日期为 {beijing_today().isoformat()}。'},
        {"role": "user", "content": question},
    ]
    first = client.chat.completions.create(
        model=model,
        messages=messages,
        tools=TOOLS,
        tool_choice="auto",
    )
    assistant_message = first.choices[0].message
    if not assistant_message.tool_calls:
        return assistant_message.content or "未能识别需要查询的城市。"

    messages.append(assistant_message.model_dump())
    date_errors = []
    forecast_dates = []
    for tool_call in assistant_message.tool_calls:
        function = AVAILABLE_FUNCTIONS.get(tool_call.function.name)
        if function is None:
            tool_result = json.dumps({"error": "未知工具"}, ensure_ascii=False)
        else:
            try:
                arguments = json.loads(tool_call.function.arguments)
                if not isinstance(arguments, dict) or set(arguments) != {'location'}:
                    raise ValueError('工具参数必须仅包含 location')
                tool_result = function(**arguments)
                tool_data = json.loads(tool_result)
                if isinstance(tool_data, dict) and tool_data.get('forecast_date'):
                    forecast_dates.append(tool_data['forecast_date'])
            except ForecastDateError as exc:
                date_errors.append(str(exc))
                tool_result = json.dumps({"error": str(exc)}, ensure_ascii=False)
            except (ValueError, TypeError, WeatherLookupError) as exc:
                tool_result = json.dumps({"error": str(exc)}, ensure_ascii=False)

        messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_call.id,
                "name": tool_call.function.name,
                "content": tool_result,
            }
        )

    answer_date = beijing_today().isoformat()
    if any(forecast_date != answer_date for forecast_date in forecast_dates):
        date_errors.append(f'查询期间已跨日，当前北京时间日期为 {answer_date}，请重新查询。')
    if date_errors:
        # Enforce freshness in code instead of relying on the model to obey a warning.
        return '本次查询有城市缺少当天有效预报，暂不生成天气结论。\n' + '\n'.join(dict.fromkeys(date_errors))

    # Refresh the date hint if the first model call or weather request crossed midnight.
    messages[0]['content'] = SYSTEM_PROMPT + f' 当前北京时间日期为 {answer_date}。'
    final = client.chat.completions.create(model=model, messages=messages)
    return final.choices[0].message.content or "天气查询完成，但模型未生成回答。"


def main() -> int:
    parser = argparse.ArgumentParser(description="GLM Function Calling 天气助手")
    parser.add_argument("question", nargs="?", default="今天北京的天气如何？")
    parser.add_argument("--model", default=None)
    args = parser.parse_args()
    try:
        print(ask_weather(args.question, args.model))
        return 0
    except (RuntimeError, ValueError) as exc:
        print(f"请求未完成：{exc}", file=sys.stderr)
        return 2
    except Exception:
        print('模型服务调用失败，请检查连接、额度与模型权限。', file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
