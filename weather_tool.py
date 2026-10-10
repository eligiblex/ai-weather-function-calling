"""Weather lookup tool used by the function-calling demo."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_CITY_CODES = Path(__file__).with_name("city_codes.json")
DEFAULT_WEATHER_API = "http://t.weather.itboy.net/api/weather/city/{city_code}"


class WeatherLookupError(RuntimeError):
    """Raised when a city cannot be resolved or the weather service fails."""


def load_city_codes(path: Path = DEFAULT_CITY_CODES) -> dict[str, str]:
    """Return a city-name to city-code mapping."""
    with path.open("r", encoding="utf-8") as file:
        records = json.load(file)
    return {item["市名"]: item["编码"] for item in records}


def get_current_weather(
    location: str,
    *,
    timeout: float = 8.0,
    session: Any = None,
) -> str:
    """Fetch current weather and return a JSON string for the LLM tool call."""
    if not isinstance(location, str) or not location.strip():
        raise WeatherLookupError('location 必须为非空城市名称')
    location = location.strip().removesuffix('市').removesuffix('区')
    city_code = load_city_codes().get(location)
    if not city_code:
        raise WeatherLookupError(f"暂不支持城市：{location}")

    if session is None:
        import requests

        session = requests

    try:
        response = session.get(
            DEFAULT_WEATHER_API.format(city_code=city_code),
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or payload.get('status', 200) != 200:
            raise ValueError('天气接口返回错误状态')
        forecast = payload["data"]["forecast"][0]
        if not isinstance(forecast, dict) or not all(forecast.get(k) for k in ('high','low','type')):
            raise ValueError('天气接口数据不完整')
    except (KeyError, IndexError, ValueError, OSError) as exc:
        raise WeatherLookupError("天气服务暂时不可用，请稍后再试") from exc
    except Exception as exc:
        raise WeatherLookupError("天气服务暂时不可用，请稍后再试") from exc

    weather = {
        "location": location,
        "high_temperature": forecast.get("high"),
        "low_temperature": forecast.get("low"),
        "week": forecast.get("week"),
        "weather_type": forecast.get("type"),
        "forecast_date": forecast.get('ymd'),
        "data_time": payload.get('time'),
        "source": "t.weather.itboy.net",
    }
    return json.dumps(weather, ensure_ascii=False)


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_current_weather",
            "description": "获取给定城市或区县的当前天气",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "城市或区县名称，例如北京、昌平",
                    }
                },
                "required": ["location"],
            },
        },
    }
]


AVAILABLE_FUNCTIONS = {"get_current_weather": get_current_weather}
