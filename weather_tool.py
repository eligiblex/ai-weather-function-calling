"""Weather lookup tool used by the function-calling demo."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any


DEFAULT_CITY_CODES = Path(__file__).with_name("city_codes.json")
DEFAULT_WEATHER_API = "http://t.weather.itboy.net/api/weather/city/{city_code}"
BEIJING_TIMEZONE = timezone(timedelta(hours=8))


class WeatherLookupError(RuntimeError):
    """Raised when a city cannot be resolved or the weather service fails."""


class ForecastDateError(WeatherLookupError):
    """The provider has no verifiable forecast for the requested Beijing date."""


def beijing_today(now: datetime | None = None) -> date:
    """Use UTC+8 regardless of the machine's timezone; allow deterministic tests."""
    instant = now if now is not None else datetime.now(timezone.utc)
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError('now 必须包含时区信息')
    return instant.astimezone(BEIJING_TIMEZONE).date()


def select_forecast(forecasts: list, target_date: date) -> dict:
    """Find the exact date, never silently fall back to yesterday or tomorrow."""
    for item in forecasts:
        if not isinstance(item, dict):
            continue
        try:
            forecast_date = date.fromisoformat(item.get('ymd', ''))
        except (TypeError, ValueError):
            continue
        if forecast_date == target_date and all(item.get(field) for field in ('high', 'low', 'type')):
            return item
    raise ForecastDateError(
        f'天气接口暂未提供北京时间 {target_date.isoformat()} 的完整有效预报，'
        '无法确认今天天气，请稍后重试；不能用其他日期的预报代替。'
    )


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
        forecasts = payload["data"]["forecast"]
        if not isinstance(forecasts, list):
            raise ValueError('天气接口数据不完整')
    except (KeyError, IndexError, ValueError, OSError) as exc:
        raise WeatherLookupError("天气服务暂时不可用，请稍后再试") from exc
    except Exception as exc:
        raise WeatherLookupError("天气服务暂时不可用，请稍后再试") from exc

    # Evaluate the date after the HTTP response, including requests crossing midnight.
    target_date = beijing_today()
    forecast = select_forecast(forecasts, target_date)

    weather = {
        "location": location,
        "high_temperature": forecast.get("high"),
        "low_temperature": forecast.get("low"),
        "week": forecast.get("week"),
        "weather_type": forecast.get("type"),
        "forecast_date": target_date.isoformat(),
        "query_date": target_date.isoformat(),
        "timezone": "UTC+08:00",
        "data_time": payload.get('time'),
        "data_note": "这是当天预报，不是即时实测；data_time 是接口更新时间，不是预报适用日期。",
        "source": "t.weather.itboy.net",
    }
    return json.dumps(weather, ensure_ascii=False)


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_current_weather",
            "description": "获取给定城市或区县北京时间当天的天气预报；不支持查询其他日期，缺少当天数据时返回错误",
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
