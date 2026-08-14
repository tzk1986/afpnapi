"""UI 录制器注入脚本生成器单元测试。"""

from postman_api_tester.services.ui_recorder_inject import get_recorder_js, get_replayer_js


class TestGetRecorderJs:
    """get_recorder_js() 脚本生成测试。"""

    def test_without_origin(self) -> None:
        code = get_recorder_js()
        assert "'use strict';" in code
        assert 'var _PROXY_ORIGIN = ""' in code
        assert "SelectorEngine" in code

    def test_with_origin(self) -> None:
        code = get_recorder_js("http://10.50.11.120:9001")
        assert '_PROXY_ORIGIN = "http://10.50.11.120:9001"' in code
        assert "'use strict';" in code

    def test_with_empty_origin(self) -> None:
        code = get_recorder_js("")
        assert 'var _PROXY_ORIGIN = ""' in code

    def test_fetch_interceptor_present(self) -> None:
        code = get_recorder_js("http://example.com")
        assert "window.fetch" in code
        assert "proxy-resource" in code

    def test_xhr_interceptor_present(self) -> None:
        code = get_recorder_js("http://example.com")
        assert "XMLHttpRequest" in code
        assert "origOpen" in code or "origSend" in code

    def test_postmessage_communication(self) -> None:
        code = get_recorder_js()
        assert "postMessage" in code
        assert "ui-recorder-event" in code

    def test_event_listeners_registered(self) -> None:
        code = get_recorder_js()
        assert "handleClick" in code
        assert "handleInput" in code
        assert "handleSubmit" in code
        assert "handleKeydown" in code


class TestGetReplayerJs:
    """get_replayer_js() 回放引擎脚本生成测试。"""

    def test_replayer_contains_basic_actions(self) -> None:
        code = get_replayer_js()
        assert "ReplayEngine" in code
        assert "_executeStep" in code
        assert "click" in code

    def test_replayer_handles_new_tab(self) -> None:
        code = get_replayer_js()
        assert "new_tab" in code
        assert "_notifyParent" in code

    def test_replayer_handles_switch_tab(self) -> None:
        """回放引擎必须包含 switch_tab 动作处理。"""
        code = get_replayer_js()
        assert "switch_tab" in code
        # 验证 switch_tab 使用 page_url / tab_url 作为 URL 来源
        assert "step.page_url" in code
        assert "step.tab_url" in code
        # 验证 switch_tab 通知父页面切换 iframe
        assert "switch_tab: true" in code

    def test_replayer_switch_tab_notifies_parent(self) -> None:
        """switch_tab 应通过 notifyParent 发送 navigate 消息。"""
        code = get_replayer_js()
        # 验证 switch_tab 块中有 navigate 通知
        assert "'navigate'" in code
        assert "switch_tab" in code
