import json
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
import app


def response(content=None, calls=None):
    message = Mock()
    message.content = content
    message.tool_calls = calls
    message.model_dump.return_value = {'role': 'assistant', 'content': content, 'tool_calls': []}
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def tool(arguments, name='get_current_weather', identifier='call-1'):
    return SimpleNamespace(id=identifier, function=SimpleNamespace(name=name, arguments=arguments))


def client_for(calls):
    client = Mock()
    client.chat.completions.create.side_effect = [response(calls=calls), response('北京晴')]
    return client


def test_tool_result_and_id_pass_to_second_generation(monkeypatch):
    weather = Mock(return_value='{"weather_type":"晴"}')
    monkeypatch.setitem(app.AVAILABLE_FUNCTIONS, 'get_current_weather', weather)
    client = client_for([tool('{"location":"北京"}')])
    assert app.ask_weather('北京天气', client=client) == '北京晴'
    weather.assert_called_once_with(location='北京')
    assert client.chat.completions.create.call_count == 2
    final = client.chat.completions.create.call_args.kwargs
    assert 'tools' not in final
    assert final['messages'][-1] == {'role': 'tool', 'name': 'get_current_weather', 'tool_call_id': 'call-1', 'content': '{"weather_type":"晴"}'}


@pytest.mark.parametrize('arguments', ['[]', 'null', '{"other":"北京"}', '{"location":"北京","extra":1}', 'not json', '__import__("os").system("echo bad")'])
def test_bad_arguments_never_execute_a_tool(monkeypatch, arguments):
    weather = Mock()
    monkeypatch.setitem(app.AVAILABLE_FUNCTIONS, 'get_current_weather', weather)
    client = client_for([tool(arguments)])
    app.ask_weather('天气', client=client)
    weather.assert_not_called()
    assert 'error' in json.loads(client.chat.completions.create.call_args.kwargs['messages'][-1]['content'])


def test_unknown_tool_is_not_executed():
    client = client_for([tool('{}', name='run_shell')])
    app.ask_weather('天气', client=client)
    assert json.loads(client.chat.completions.create.call_args.kwargs['messages'][-1]['content']) == {'error': '未知工具'}


def test_multiple_tools_keep_matching_ids(monkeypatch):
    monkeypatch.setitem(app.AVAILABLE_FUNCTIONS, 'get_current_weather', lambda location: json.dumps({'location': location}))
    client = client_for([tool('{"location":"北京"}', identifier='one'), tool('{"location":"上海"}', identifier='two')])
    app.ask_weather('两地天气', client=client)
    messages = client.chat.completions.create.call_args.kwargs['messages'][-2:]
    assert [m['tool_call_id'] for m in messages] == ['one', 'two']


def test_direct_answer_without_tool():
    client = Mock()
    client.chat.completions.create.return_value = response('你好')
    assert app.ask_weather('你好', client=client) == '你好'
    assert client.chat.completions.create.call_count == 1


@pytest.mark.parametrize('question', ['', '   ', 'a' * 1001, None])
def test_invalid_questions(question):
    client = Mock()
    with pytest.raises(ValueError):
        app.ask_weather(question, client=client)
    client.chat.completions.create.assert_not_called()


def test_missing_key(monkeypatch):
    monkeypatch.delenv('ZHIPUAI_API_KEY', raising=False)
    monkeypatch.delenv('ZHIPU_API_KEY', raising=False)
    monkeypatch.setattr(app, 'load_dotenv', lambda *args: None)
    with pytest.raises(RuntimeError, match='ZHIPUAI_API_KEY'):
        app.build_client()
