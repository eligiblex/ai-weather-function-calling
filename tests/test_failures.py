import json
from unittest.mock import Mock
import pytest
import requests
from weather_tool import WeatherLookupError, get_current_weather


@pytest.mark.parametrize('payload', [{}, [], {'status': 500}, {'data': {'forecast': []}}, {'data': {'forecast': [{}]}}, {'data': None}])
def test_malformed_provider_payload(payload):
    session = Mock()
    session.get.return_value.json.return_value = payload
    with pytest.raises(WeatherLookupError):
        get_current_weather('北京', session=session)


@pytest.mark.parametrize('location', ['', ' ', 123, None])
def test_location_validation_before_network(location):
    session = Mock()
    with pytest.raises(WeatherLookupError):
        get_current_weather(location, session=session)
    session.get.assert_not_called()


def test_timeout_is_friendly():
    session = Mock()
    session.get.side_effect = requests.Timeout('internal network details')
    with pytest.raises(WeatherLookupError, match='天气服务暂时不可用'):
        get_current_weather('北京', session=session)
    assert session.get.call_args.kwargs['timeout'] == 8.0


def test_suffix_and_provenance():
    session = Mock()
    session.get.return_value.json.return_value = {'status': 200, 'time': '2026-10-10 10:00', 'data': {'forecast': [{'high': '22', 'low': '12', 'type': '晴', 'ymd': '2026-10-10'}]}}
    result = json.loads(get_current_weather(' 北京市 ', session=session))
    assert result['location'] == '北京'
    assert result['forecast_date'] == '2026-10-10'
    assert result['source'] == 't.weather.itboy.net'
