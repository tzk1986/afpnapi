"""Headless 执行子进程入口。

在独立进程中运行 Playwright，避免与 Waitress 线程池的 greenlet 冲突。
通过 JSON 文件传递输入数据（避免 stdin 管道编码问题）。
"""

import json
import sys
import traceback
from pathlib import Path
from typing import Any, Dict, List

# 确保项目根目录在 sys.path 中
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def _write_output(data: Dict[str, Any]) -> None:
    """以 UTF-8 编码向 stdout 写入一行 JSON 输出（避免 Windows GBK 编码问题）。"""
    json_str = json.dumps(data, ensure_ascii=False, default=str)
    sys.stdout.buffer.write(json_str.encode("utf-8") + b"\n")
    sys.stdout.buffer.flush()


def _write_line(text: str) -> None:
    """以 UTF-8 编码向 stdout 写入一行纯文本。"""
    sys.stdout.buffer.write(text.encode("utf-8") + b"\n")
    sys.stdout.buffer.flush()


def main() -> None:
    """从 JSON 文件读取输入，执行 headless 测试，向 stdout 输出结果。"""
    input_file = sys.argv[1] if len(sys.argv) > 1 else None
    if not input_file:
        error_output: Dict[str, Any] = {
            "success": False,
            "error": "缺少输入文件参数",
        }
        _write_output(error_output)
        sys.exit(1)

    try:
        with open(input_file, "r", encoding="utf-8") as f:
            input_data = json.load(f)

        case_data: Dict[str, Any] = input_data["case_data"]
        options: Dict[str, Any] = input_data["options"]
        job_id: str = input_data["job_id"]
        screenshots_dir: str | None = input_data.get("screenshots_dir")

        from postman_api_tester.services.ui_headless_engine import UiHeadlessEngine

        engine = UiHeadlessEngine(
            browser_type=options.get("headless_browser", "chromium"),
            screenshots_dir=Path(screenshots_dir) if screenshots_dir else None,
        )

        steps: List[Dict[str, Any]] = case_data.get("steps", [])
        base_url: str = case_data.get("base_url", "")

        summary = engine.execute(
            steps=steps,
            base_url=base_url,
            options=options,
            job_id=job_id,
            on_browser_ready=lambda: _write_line("BROWSER_READY"),
            on_step_complete=lambda _idx, step_result: _write_output(
                {"step": step_result}
            ),
        )

        step_results: List[Dict[str, Any]] = summary.pop("_step_results", [])

        output: Dict[str, Any] = {
            "success": True,
            "summary": summary,
            "step_results": step_results,
        }
        _write_output(output)

    except Exception as e:
        error_output: Dict[str, Any] = {
            "success": False,
            "error": str(e)[:500],
            "traceback": traceback.format_exc()[-2000:],
        }
        _write_output(error_output)
        sys.exit(1)


if __name__ == "__main__":
    main()
