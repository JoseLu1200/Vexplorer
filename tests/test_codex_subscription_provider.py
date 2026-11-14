import pytest
import time

from tools.codex_subscription_provider import convert_input, isolated_command, CodexSubscriptionProvider
from backend.app.agente.config import ProviderSettings
from backend.app.agente.provider import ProviderError


def test_converts_public_text_images_without_dropping_visual_evidence():
    assert convert_input([{'role': 'user', 'content': [
        {'type': 'input_text', 'text': 'Inspect contour A.'},
        {'type': 'input_image', 'image_url': 'data:image/png;base64,YQ==', 'detail': 'high'},
    ]}]) == [{'type': 'text', 'text': 'Inspect contour A.'},
             {'type': 'image', 'url': 'data:image/png;base64,YQ==', 'detail': 'high'}]
    with pytest.raises(ValueError):
        convert_input([{'role': 'user', 'content': [{'type': 'file', 'path': 'private.json'}]}])


def test_subscription_command_disables_connected_tools_and_forces_chatgpt():
    command = isolated_command('codex', {'mcp_servers': {'github': {}, 'node_repl': {}},
                                        'plugins': {'documents@runtime': {}}})
    assert 'forced_login_method="chatgpt"' in command
    assert 'mcp_servers.github.enabled=false' in command
    assert 'mcp_servers.node_repl.enabled=false' in command
    assert 'plugins.documents@runtime.enabled=false' in command
    assert 'features.shell_tool=false' in command
    assert 'web_search="disabled"' in command


def test_native_tool_feedback_and_history_are_case_local(monkeypatch):
    provider = CodexSubscriptionProvider(ProviderSettings(None, 'gpt-6.1-sol'),
                                         instructions='test', executable='codex')
    provider.process = object()
    provider.thread_id = 'fixture-thread'
    sent = []
    monkeypatch.setattr(provider, '_send', sent.append)
    monkeypatch.setattr(provider, '_rpc', lambda *args: {})
    monkeypatch.setattr(provider, 'close', lambda: None)
    tools = [{'name': 'inspect', 'parameters': {'type': 'object'}}]
    for index in (1, 2):
        provider.messages.put({'id': index + 20, 'method': 'item/tool/call', 'params': {
            'tool': 'inspect', 'callId': f'call-{index}', 'arguments': {'contour': 'A'}}})
    first = provider.create_response(input_items=[{'role': 'user', 'content': 'public input'}],
                                     tools=tools, previous_response_id=None, timeout_s=10)
    second = provider.create_response(input_items=[{'type': 'function_call_output',
        'call_id': 'call-1', 'output': '{"dimension":42}'}], tools=tools,
        previous_response_id=first.id, timeout_s=10)
    assert second.tool_calls[0].call_id == 'call-2'
    assert sent == [{'id': 21, 'result': {'contentItems': [
        {'type': 'inputText', 'text': '{"dimension":42}'}], 'success': True}}]
    with pytest.raises(ProviderError, match='history_mismatch'):
        provider.create_response(input_items=[], tools=tools, previous_response_id='other-case', timeout_s=10)


def test_expired_deadline_rejects_already_queued_response(monkeypatch):
    provider = CodexSubscriptionProvider(ProviderSettings(None, 'gpt-6.1-sol'),
                                         instructions='test', executable='codex')
    monkeypatch.setattr(provider, 'close', lambda: None)
    provider.messages.put({'result': 'late'})
    with pytest.raises(ProviderError, match='timeout'):
        provider._next(time.monotonic() - 1)
