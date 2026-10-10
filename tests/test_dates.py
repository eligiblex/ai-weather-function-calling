from datetime import date, datetime
import json
from unittest.mock import Mock
import pytest
import app
import weather_tool
from weather_tool import ForecastDateError, beijing_today, get_current_weather
from test_app import client_for, tool


TODAY = date(2026, 10, 11)


def forecast(day, kind='晴'):
    return {'ymd': day, 'high': '高温25℃', 'low': '低温15℃', 'type': kind}


def session_for(forecasts):
    session = Mock()
    session.get.return_value.json.return_value = {
        'status': 200, 'time': '2026-10-10 23:00:00', 'data': {'forecast': forecasts}
    }
    return session


@pytest.fixture(autouse=True)
def freeze_date(monkeypatch):
    monkeypatch.setattr(weather_tool, 'beijing_today', lambda: TODAY)


def test_find_today_instead_of_first_forecast():
    result = json.loads(get_current_weather('北京', session=session_for([
        forecast('2026-10-10', '雨'), forecast('2026-10-11', '晴'), forecast('2026-10-12', '雪')
    ])))
    assert result['forecast_date'] == result['query_date'] == '2026-10-11'
    assert result['weather_type'] == '晴'
    assert result['data_time'] == '2026-10-10 23:00:00'
    assert result['timezone'] == 'UTC+08:00'


@pytest.mark.parametrize('forecasts', [
    [forecast('2026-10-10')], [forecast('2026-10-12')], [],
    [forecast('')], [forecast('not-a-date')], [forecast(None)],
    [{'ymd': '2026-10-11'}], [None, 123, 'bad'],
])
def test_missing_stale_future_invalid_or_incomplete_today_is_rejected(forecasts):
    with pytest.raises(ForecastDateError, match='2026-10-11'):
        get_current_weather('北京', session=session_for(forecasts))


def test_order_and_malformed_other_days_do_not_hide_valid_today():
    result = json.loads(get_current_weather('北京', session=session_for([
        None, forecast('2026-10-13'), {'ymd': '2026-10-11'}, forecast('2026-10-11', '多云')
    ])))
    assert result['weather_type'] == '多云'


@pytest.mark.parametrize(('utc_time', 'expected'), [
    ('2026-10-10T15:59:59+00:00', date(2026, 10, 10)),
    ('2026-10-10T16:00:00+00:00', date(2026, 10, 11)),
    ('2026-12-31T16:00:00+00:00', date(2027, 1, 1)),
])
def test_beijing_date_independent_of_system_timezone(utc_time, expected):
    assert beijing_today(datetime.fromisoformat(utc_time)) == expected


def test_naive_datetime_rejected():
    with pytest.raises(ValueError, match='时区'):
        beijing_today(datetime(2026, 10, 11))


def test_date_checked_after_network_response(monkeypatch):
    events = []
    session = session_for([forecast('2026-10-11')])
    session.get.side_effect = lambda *args, **kwargs: events.append('http') or session.get.return_value
    monkeypatch.setattr(weather_tool, 'beijing_today', lambda: events.append('date') or TODAY)
    get_current_weather('北京', session=session)
    assert events == ['http', 'date']


def test_date_error_is_not_sent_to_another_generation(monkeypatch):
    def old_data(location):
        raise ForecastDateError('无当天预报，不可使用旧数据')
    monkeypatch.setitem(app.AVAILABLE_FUNCTIONS, 'get_current_weather', old_data)
    client = client_for([tool('{"location":"北京"}')])
    answer = app.ask_weather('北京今天的天气', client=client)
    assert '缺少当天有效预报' in answer
    assert '不可使用旧数据' in answer
    assert client.chat.completions.create.call_count == 1


def test_midnight_before_final_generation_requires_retry(monkeypatch):
    monkeypatch.setattr(app, 'beijing_today', Mock(side_effect=[date(2026, 10, 10), TODAY]))
    monkeypatch.setitem(app.AVAILABLE_FUNCTIONS, 'get_current_weather', lambda location: json.dumps({'forecast_date': '2026-10-10', 'weather_type': '晴'}))
    client = client_for([tool('{"location":"北京"}')])
    assert '已跨日' in app.ask_weather('北京天气', client=client)
    assert client.chat.completions.create.call_count == 1


def test_prompt_and_tool_result_have_explicit_correct_date(monkeypatch):
    monkeypatch.setattr(app, 'beijing_today', lambda: TODAY)
    monkeypatch.setitem(app.AVAILABLE_FUNCTIONS, 'get_current_weather', lambda location: json.dumps({'forecast_date': '2026-10-11', 'weather_type': '晴'}))
    client = client_for([tool('{"location":"北京"}')])
    app.ask_weather('北京天气', client=client)
    messages = client.chat.completions.create.call_args.kwargs['messages']
    assert '2026-10-11' in messages[0]['content']
    assert '具体年月日' in messages[0]['content']
    assert json.loads(messages[-1]['content'])['forecast_date'] == '2026-10-11'
