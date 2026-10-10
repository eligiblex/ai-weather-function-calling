import json
import unittest
from unittest.mock import Mock

from weather_tool import WeatherLookupError, get_current_weather, load_city_codes


class WeatherToolTests(unittest.TestCase):
    def test_city_code_file_can_be_loaded(self):
        city_codes = load_city_codes()
        self.assertEqual(city_codes["北京"], "101010100")

    def test_unknown_city_is_rejected_before_network_call(self):
        with self.assertRaises(WeatherLookupError):
            get_current_weather("不存在的城市")

    def test_weather_response_is_normalized(self):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "data": {
                "forecast": [
                    {"high": "高温 22℃", "low": "低温 12℃", "week": "星期五", "type": "晴"}
                ]
            }
        }
        session = Mock()
        session.get.return_value = response

        result = json.loads(get_current_weather("北京", session=session))
        self.assertEqual(result["weather_type"], "晴")
        session.get.assert_called_once()


if __name__ == "__main__":
    unittest.main()
