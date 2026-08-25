"""Phase 3 功能测试脚本：模拟完整录制 + localStorage 提取 + 认证档案创建流程。

运行方式：
1. 先启动后端: python -m postman_api_tester
2. 再运行本脚本: python tests/functional_test_local_storage.py

或者使用 Flask 测试客户端运行（不需要启动服务器）。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

# 添加项目根目录到 path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def run_standalone_test() -> None:
    """独立运行测试（使用 Flask 测试客户端）。"""
    from flask import Flask

    from postman_api_tester.handlers.ui_testing_routes import (
        api_ui_testing_recording_local_storage,
        api_ui_testing_recording_start,
        api_ui_testing_recording_stop,
    )
    from postman_api_tester.services.ui_auth_profile_store import UiAuthProfileStore

    app = Flask(__name__)
    app.config["TESTING"] = True

    print("=" * 70)
    print("Phase 3 功能测试：localStorage 全链路")
    print("=" * 70)

    # Step 1: 创建录制会话
    print("\n[Step 1] 创建录制会话...")
    with app.test_request_context(
        "/api/ui-testing/recording/start",
        method="POST",
        json={"base_url": "http://test.example.com"},
    ):
        resp = api_ui_testing_recording_start()
        resp_data = json.loads(resp[0].get_data(as_text=True))
        session_id = resp_data["data"]["session_id"]
        print(f"  [OK] 录制会话已创建: {session_id}")

    # Step 2: 模拟浏览器注入 localStorage 并上报
    print("\n[Step 2] 模拟浏览器上报 localStorage...")
    ls_data = {
        "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test",
        "user_name": "test_user",
        "user_role": "admin",
        "theme": "dark",
        "last_login": "2026-08-25T10:00:00",
    }
    with app.test_request_context(
        "/api/ui-testing/recording/local-storage",
        method="POST",
        json={
            "session_id": session_id,
            "origin": "http://test.example.com",
            "local_storage": ls_data,
        },
    ):
        resp = api_ui_testing_recording_local_storage()
        resp_data = json.loads(resp[0].get_data(as_text=True))
        assert resp_data["data"]["ok"] is True
        assert resp_data["data"]["stored"] is True
        print(f"  [OK] localStorage 已上报 ({len(ls_data)} 个键)")

    # Step 3: 停止录制，验证 localStorage 导出
    print("\n[Step 3] 停止录制并验证 localStorage 导出...")
    with app.test_request_context(
        "/api/ui-testing/recording/stop",
        method="POST",
        json={"session_id": session_id},
    ):
        resp = api_ui_testing_recording_stop()
        resp_data = json.loads(resp[0].get_data(as_text=True))
        data = resp_data["data"]
        exported_ls = data["local_storage_for_export"]
        print(f"  [OK] 录制已停止 (步数: {data['step_count']})")
        print(f"  [OK] localStorage 已导出 ({len(exported_ls)} 个键)")
        assert exported_ls == ls_data, f"Expected {ls_data}, got {exported_ls}"
        print(f"  [OK] 导出数据匹配: {list(exported_ls.keys())}")

    # Step 4: 创建认证档案
    print("\n[Step 4] 创建认证档案...")
    import tempfile

    tmp_dir = tempfile.mkdtemp()
    auth_store = UiAuthProfileStore(profiles_dir=Path(tmp_dir))
    profile_id = auth_store.save_profile({
        "name": "功能测试档案",
        "description": "Phase 3 localStorage 功能测试",
        "base_url": "http://test.example.com",
        "cookies": [
            {
                "name": "session_id",
                "value": "abc123",
                "domain": "test.example.com",
                "path": "/",
            }
        ],
        "local_storage": exported_ls,
        "source": "recording",
    })
    print(f"  [OK] 认证档案已创建: {profile_id}")

    # Step 5: 导出 storage_state
    print("\n[Step 5] 导出 Playwright storage_state...")
    state = auth_store.export_storage_state(profile_id)
    assert state is not None
    assert len(state["cookies"]) == 1
    assert len(state["origins"]) == 1
    origin = state["origins"][0]
    assert origin["origin"] == "http://test.example.com"
    ls_items = origin["localStorage"]
    print(f"  [OK] storage_state 导出成功:")
    print(f"     - Cookies: {len(state['cookies'])} 条")
    print(f"     - Origins: {len(state['origins'])} 个")
    print(f"     - localStorage 条目: {len(ls_items)} 个")
    for item in ls_items:
        print(f"       - {item['name']}: {item['value'][:30]}...")

    # Step 6: 验证 storage_state JSON 格式符合 Playwright 规范
    print("\n[Step 6] 验证 storage_state JSON 格式...")
    state_json = json.dumps(state, ensure_ascii=False, indent=2)
    parsed = json.loads(state_json)
    assert "cookies" in parsed
    assert "origins" in parsed
    for cookie in parsed["cookies"]:
        assert "name" in cookie
        assert "value" in cookie
        assert "domain" in cookie
    for origin_item in parsed["origins"]:
        assert "origin" in origin_item
        assert "localStorage" in origin_item
        for ls_item in origin_item["localStorage"]:
            assert "name" in ls_item
            assert "value" in ls_item
    print(f"  [OK] storage_state JSON 格式正确")
    print(f"\n{state_json}")

    # Cleanup
    import shutil
    shutil.rmtree(tmp_dir, ignore_errors=True)

    print("\n" + "=" * 70)
    print("Phase 3 功能测试全部通过！[OK]")
    print("=" * 70)


def run_multi_origin_test() -> None:
    """测试多 origin localStorage 合并场景。"""
    from flask import Flask

    from postman_api_tester.handlers.ui_testing_routes import (
        api_ui_testing_recording_local_storage,
        api_ui_testing_recording_start,
        api_ui_testing_recording_stop,
    )

    app = Flask(__name__)
    app.config["TESTING"] = True

    print("\n" + "=" * 70)
    print("多 Origin localStorage 合并测试")
    print("=" * 70)

    # Step 1: 创建录制会话
    with app.test_request_context(
        "/api/ui-testing/recording/start",
        method="POST",
        json={"base_url": "http://platform.example.com"},
    ):
        resp = api_ui_testing_recording_start()
        resp_data = json.loads(resp[0].get_data(as_text=True))
        session_id = resp_data["data"]["session_id"]
    print(f"\n[Step 1] 录制会话: {session_id}")

    # Step 2: 模拟多个 origin 上报 localStorage
    # (跨域 iframe 场景：主平台 + API 子系统)
    origins_data = [
        ("http://platform.example.com", {"token": "main_token", "user": "admin"}),
        ("http://api.example.com", {"api_key": "sub_key", "config": "{}"}),
    ]
    for origin, ls_data in origins_data:
        with app.test_request_context(
            "/api/ui-testing/recording/local-storage",
            method="POST",
            json={
                "session_id": session_id,
                "origin": origin,
                "local_storage": ls_data,
            },
        ):
            resp = api_ui_testing_recording_local_storage()
            resp_data = json.loads(resp[0].get_data(as_text=True))
            print(f"  [OK] {origin}: {list(ls_data.keys())}")

    # Step 3: 停止录制，验证合并
    with app.test_request_context(
        "/api/ui-testing/recording/stop",
        method="POST",
        json={"session_id": session_id},
    ):
        resp = api_ui_testing_recording_stop()
        resp_data = json.loads(resp[0].get_data(as_text=True))
        data = resp_data["data"]
        exported_ls = data["local_storage_for_export"]
        print(f"\n[Step 2] 合并后 localStorage ({len(exported_ls)} 个键):")
        for k, v in exported_ls.items():
            print(f"  - {k}: {v}")

        # 验证所有键都包含在合并结果中
        expected_keys = {"token", "user", "api_key", "config"}
        actual_keys = set(exported_ls.keys())
        assert expected_keys == actual_keys, f"Expected {expected_keys}, got {actual_keys}"

    print("\n[OK] 多 Origin 合并测试通过！")


if __name__ == "__main__":
    run_standalone_test()
    run_multi_origin_test()
    print("\n[OK] 全部功能测试完成！")
