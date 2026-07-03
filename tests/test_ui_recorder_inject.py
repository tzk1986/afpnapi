"""UI 录制器注入脚本生成器单元测试。"""

from postman_api_tester.services.ui_recorder_inject import get_recorder_js


class TestGetRecorderJs:
    """get_recorder_js() 脚本生成测试。"""

    def test_without_origin(self) -> None:
        code = get_recorder_js()
        assert "'use strict';" in code
        assert 'var _PROXY_ORIGIN = "' not in code
        assert "SelectorEngine" in code

    def test_with_origin(self) -> None:
        code = get_recorder_js("http://10.50.11.120:9001")
        assert '_PROXY_ORIGIN = "http://10.50.11.120:9001"' in code
        assert "'use strict';" in code

    def test_with_empty_origin(self) -> None:
        code = get_recorder_js("")
        assert 'var _PROXY_ORIGIN = "' not in code

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
