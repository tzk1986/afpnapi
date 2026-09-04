"""v1.38.0 UI 自愈端到端冒烟（S2.3 / V5-5）。

双 skipif：playwright 未安装 → 跳；chromium 启动失败 → 跳（跳 ≠ 红）。
场景：
  1. 开关开 + 坏选择器 + element_info.test_id 完好 → test_id 策略命中通过
  2. 开关关（默认）同场景 → 步骤 failed、无 heal 键（零回归对照）
  3. 回放引擎无自愈引用（锁定"自愈仅无头"现状，N3）
"""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

import postman_api_tester.services.ui_headless_engine as engine_mod
from postman_api_tester.services import ui_healing, ui_recorder_inject
from postman_api_tester.services.ui_headless_engine import (
    UiHeadlessEngine,
    is_playwright_available,
)

pytestmark = pytest.mark.skipif(
    not is_playwright_available(), reason="playwright 未安装"
)

_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>heal-smoke</title></head>
<body>
<button id="real-btn" data-testid="submit-btn">提交</button>
<div id="msg"></div>
</body></html>
"""


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = _HTML.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def page_url():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/"
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture(scope="module")
def chromium():
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"playwright 不可导入: {e}")
    pw = None
    try:
        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=True)
        browser.close()
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"chromium 启动失败: {e}")
    finally:
        if pw is not None:
            try:
                pw.stop()
            except Exception:  # noqa: BLE001
                pass


def _steps(url: str):
    return [
        {"action": "navigate", "value": url},
        {
            "action": "click",
            "selector": {
                "primary": "#gone",
                "fallback_css": "",
                "fallback_xpath": "",
            },
            "element_info": {
                "tag": "button",
                "test_id": "submit-btn",
                "text": "提交",
                "aria_label": "",
            },
            "value": "",
        },
    ]


def _run(monkeypatch, url, enabled, job_id, tmp_path):
    monkeypatch.setattr(engine_mod, "UI_SELF_HEALING_ENABLED", enabled)
    events = []
    monkeypatch.setattr(
        ui_healing,
        "_LOG_SINK",
        lambda jid, idx, payload: events.append(payload),
    )
    engine = UiHeadlessEngine(screenshots_dir=tmp_path)
    summary = engine.execute(
        _steps(url),
        "",
        {"timeout": 3000, "delay_between_steps": 0},
        job_id,
    )
    return summary, events


def test_smoke_heal_testid(monkeypatch, chromium, page_url, tmp_path):
    summary, events = _run(monkeypatch, page_url, True, "smoke-on", tmp_path)
    click = summary["_step_results"][1]
    assert click["status"] == "passed"
    assert click.get("healed") is True
    info = click.get("heal_info") or {}
    assert info.get("strategy") == "test_id"
    assert info.get("confidence") == 95
    assert info.get("old_selector") == "#gone"
    assert "submit-btn" in info.get("new_selector", "")
    assert summary["healed_steps"] == 1

    names = [e.get("event") for e in events]
    assert "self_healing.attempt" in names
    assert "self_healing.healed" in names
    assert list(tmp_path.rglob("step_1_healed.png")), "healed 截图应落盘"


def test_smoke_disabled_no_heal(monkeypatch, chromium, page_url, tmp_path):
    summary, events = _run(monkeypatch, page_url, False, "smoke-off", tmp_path)
    click = summary["_step_results"][1]
    assert click["status"] == "failed"
    assert "healed" not in click
    assert "heal_info" not in click
    assert summary["healed_steps"] == 0
    assert not [
        e for e in events if str(e.get("event", "")).startswith("self_healing")
    ]


def test_replay_engine_not_touched_by_healing():
    """回放引擎零自愈引用（"仅无头支持"现状锁定；红线文件防混改哨兵）。"""
    src = Path(ui_recorder_inject.__file__).read_text(encoding="utf-8")
    assert "ui_healing" not in src
    assert "self_healing" not in src
