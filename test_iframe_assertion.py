"""实际测试：验证 assert_text_exists 的 iframe 支持。

运行方式：
    python test_iframe_assertion.py

测试内容：
    1. 创建包含 iframe 的 HTML 页面
    2. 使用 Playwright 打开页面
    3. 验证能在 iframe 中找到文本
"""

import tempfile
import time
from pathlib import Path
from playwright.sync_api import sync_playwright
from postman_api_tester.services.ui_headless_engine import UiHeadlessEngine


def create_test_html():
    """创建包含 iframe 的测试 HTML 文件。"""
    # 主页面
    main_html = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>测试页面</title>
    </head>
    <body>
        <h1>主框架标题</h1>
        <p>这是主页面的文本内容。</p>
        <iframe id="test-iframe" src="iframe_content.html" width="500" height="300"></iframe>
    </body>
    </html>
    """

    # iframe 内容页面
    iframe_html = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Iframe 内容</title>
    </head>
    <body>
        <h2>Iframe 标题</h2>
        <p>这是 iframe 中的文本内容。</p>
        <div class="supplier-info">
            <strong>供应商名称：</strong>测试供应商A
        </div>
        <p>iframe 底部文本。</p>
    </body>
    </html>
    """

    # 创建临时目录
    temp_dir = tempfile.mkdtemp()
    main_path = Path(temp_dir) / "main.html"
    iframe_path = Path(temp_dir) / "iframe_content.html"

    main_path.write_text(main_html, encoding="utf-8")
    iframe_path.write_text(iframe_html, encoding="utf-8")

    return main_path, temp_dir


def test_iframe_text_detection():
    """测试能否在 iframe 中找到文本。"""
    print("=" * 60)
    print("测试：assert_text_exists 的 iframe 支持")
    print("=" * 60)

    # 创建测试文件
    main_path, temp_dir = create_test_html()
    print(f"[PASS] 创建测试文件：{main_path}")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            # 打开测试页面
            page.goto(f"file://{main_path}")
            page.wait_for_load_state("networkidle")
            print("[PASS] 页面已加载")

            # 创建引擎实例
            engine = UiHeadlessEngine.__new__(UiHeadlessEngine)

            # 测试 1：在主框架中查找文本（应该找到）
            print("\n测试 1：查找主框架文本 '主框架标题'")
            result = engine._action_assert_text_exists(page, "主框架标题", 5000)
            print(f"  状态：{result['status']}")
            print(f"  匹配数：{result.get('match_count', 0)}")
            assert result["status"] == "passed", "应该找到主框架文本"
            assert result["match_count"] >= 1, "匹配数应 >= 1"
            print("  [PASS] 通过")

            # 测试 2：在 iframe 中查找文本（应该找到）
            print("\n测试 2：查找 iframe 文本 '供应商名称'")
            result = engine._action_assert_text_exists(page, "供应商名称", 5000)
            print(f"  状态：{result['status']}")
            print(f"  匹配数：{result.get('match_count', 0)}")
            assert result["status"] == "passed", "应该找到 iframe 中的文本"
            assert result["match_count"] >= 1, "匹配数应 >= 1"
            print("  [PASS] 通过")

            # 测试 3：查找不存在的文本（应该失败）
            print("\n测试 3：查找不存在的文本 '不存在的文本XYZ123'")
            result = engine._action_assert_text_exists(page, "不存在的文本XYZ123", 3000)
            print(f"  状态：{result['status']}")
            print(f"  错误信息：{result['error'][:100]}...")
            assert result["status"] == "failed", "应该找不到不存在的文本"
            assert "页面文本预览" in result["error"], "错误信息应包含页面预览"
            assert "当前 URL" in result["error"], "错误信息应包含当前 URL"
            print("  [PASS] 通过（预期失败）")

            # 测试 4：验证错误信息包含诊断内容
            print("\n测试 4：验证错误信息包含完整诊断内容")
            assert "已扫描" in result["error"], "错误信息应包含 frame 数量"
            print(f"  完整错误信息：\n{result['error']}")
            print("  [PASS] 通过")

            browser.close()
            print("\n" + "=" * 60)
            print("[PASS] 所有测试通过！")
            print("=" * 60)

    finally:
        # 清理临时文件
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)
        print(f"[PASS] 清理临时文件：{temp_dir}")


if __name__ == "__main__":
    test_iframe_text_detection()
