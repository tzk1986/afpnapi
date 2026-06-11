"""report_judgement_service 单元测试."""

import json
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest

from postman_api_tester.services.report_judgement_service import (
    set_report_result_judgement,
)


def _make_meta(results: List[Dict[str, Any]], summary: Dict[str, Any]) -> Dict[str, Any]:
    return {"results": results, "summary": summary}


def _write_meta(meta_path: Path, meta: Dict[str, Any]) -> None:
    with meta_path.open("w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)


class MockLock:
    """Simple mock context manager for lock."""
    def __enter__(self):
        return None
    def __exit__(self, exc_type, exc_val, exc_tb):
        return False


class TestOverride:
    """override 操作: 人工标记结果为 PASSED 或 FAILED."""

    def test_override_passed(self, tmp_path: Path) -> None:
        deps = MagicMock()
        deps.get_report_write_lock.return_value = MockLock()
        deps.find_report.return_value = {"meta_file": "_meta.json"}

        results = [{
            "name": "API Check", "folder": "", "method": "POST",
            "url": "https://api.example.com/users", "status": "FAILED",
            "message": "Expected 201 got 500", "expected_status": 201,
            "item_path": [], "manual_judgement": {},
            "judgement_history": [],
        }]
        _write_meta(tmp_path / "_meta.json", _make_meta(results, {
            "total": 1, "passed": 0, "failed": 1, "error": 0, "success_rate": 0.0,
        }))
        deps.compute_summary.side_effect = lambda rs: {"total": 1, "passed": 1, "failed": 0, "error": 0, "success_rate": 1.0}
        deps.invalidate_reports_cache.reset_mock()

        result = set_report_result_judgement(
            report_name="my_report", result_index=0, action="override",
            target_status="PASSED", reason="False positive",
            reports_dir=tmp_path,
            get_report_write_lock=deps.get_report_write_lock,
            find_report=deps.find_report,
            compute_summary=deps.compute_summary,
            invalidate_reports_cache=deps.invalidate_reports_cache,
        )

        assert result["result"]["status"] == "PASSED"
        mj = result["result"]["manual_judgement"]
        assert mj["active"] is True
        assert mj["source"] == "manual"
        assert mj["action"] == "override"
        assert mj["target_status"] == "PASSED"
        assert mj["reason"] == "False positive"
        assert mj["from_status"] == "FAILED"
        assert len(result["result"]["judgement_history"]) == 1
        deps.compute_summary.assert_called_once()
        deps.invalidate_reports_cache.assert_called_once()

        with (tmp_path / "_meta.json").open("r") as f:
            saved = json.load(f)
        assert saved["results"][0]["status"] == "PASSED"

    def test_override_failed(self, tmp_path: Path) -> None:
        deps = MagicMock()
        deps.get_report_write_lock.return_value = MockLock()
        deps.find_report.return_value = {"meta_file": "_meta.json"}

        results = [{
            "name": "Health", "folder": "", "method": "GET",
            "url": "https://example.com/health", "status": "PASSED",
            "message": "OK", "expected_status": 200,
            "item_path": [], "manual_judgement": {},
            "judgement_history": [],
        }]
        _write_meta(tmp_path / "_meta.json", _make_meta(results, {
            "total": 1, "passed": 1, "failed": 0, "error": 0, "success_rate": 1.0,
        }))
        deps.compute_summary.side_effect = lambda rs: {"total": 1, "passed": 0, "failed": 1, "error": 0, "success_rate": 0.0}

        result = set_report_result_judgement(
            report_name="r", result_index=0, action="override",
            target_status="FAILED", reason="Service degraded",
            reports_dir=tmp_path,
            get_report_write_lock=deps.get_report_write_lock,
            find_report=deps.find_report,
            compute_summary=deps.compute_summary,
            invalidate_reports_cache=MagicMock(),
        )

        assert result["result"]["status"] == "FAILED"
        assert result["result"]["manual_judgement"]["active"] is True
        assert result["result"]["manual_judgement"]["from_status"] == "PASSED"

    def test_override_preserves_other_fields(self, tmp_path: Path) -> None:
        deps = MagicMock()
        deps.get_report_write_lock.return_value = MockLock()
        deps.find_report.return_value = {"meta_file": "_meta.json"}

        results = [{
            "name": "Nest API", "folder": "v2", "method": "PUT",
            "url": "https://api.example.com/v2/item/42", "status": "FAILED",
            "message": "Timeout", "expected_status": 200,
            "item_path": ["Users", "Details"], "manual_judgement": {},
            "judgement_history": [], "custom_field": "kept",
        }]
        _write_meta(tmp_path / "_meta.json", _make_meta(results, {
            "total": 1, "passed": 0, "failed": 1, "error": 0, "success_rate": 0.0,
        }))
        deps.compute_summary.side_effect = lambda rs: {"total": 1, "passed": 1, "failed": 0, "error": 0, "success_rate": 1.0}

        set_report_result_judgement(
            report_name="r", result_index=0, action="override",
            target_status="PASSED", reason="", reports_dir=tmp_path,
            get_report_write_lock=deps.get_report_write_lock,
            find_report=deps.find_report,
            compute_summary=deps.compute_summary,
            invalidate_reports_cache=MagicMock(),
        )

        with (tmp_path / "_meta.json").open("r") as f:
            saved = json.load(f)
        row = saved["results"][0]
        assert row["name"] == "Nest API"
        assert row["folder"] == "v2"
        assert row["method"] == "PUT"
        assert row["item_path"] == ["Users", "Details"]
        assert row["custom_field"] == "kept"

    def test_override_multiple_results_change_summary(self, tmp_path: Path) -> None:
        deps = MagicMock()
        deps.get_report_write_lock.return_value = MockLock()
        deps.find_report.return_value = {"meta_file": "_meta.json"}

        results = [
            {"name": "A", "status": "PASSED", "message": "ok", "method": "GET", "url": "http://a",
             "expected_status": 200, "item_path": [], "folder": "", "manual_judgement": {}, "judgement_history": []},
            {"name": "B", "status": "FAILED", "message": "err", "method": "POST", "url": "http://b",
             "expected_status": 200, "item_path": [], "folder": "", "manual_judgement": {}, "judgement_history": []},
            {"name": "C", "status": "PASSED", "message": "ok", "method": "GET", "url": "http://c",
             "expected_status": 200, "item_path": [], "folder": "", "manual_judgement": {}, "judgement_history": []},
        ]
        _write_meta(tmp_path / "_meta.json", _make_meta(results, {
            "total": 3, "passed": 2, "failed": 1, "error": 0, "success_rate": 2/3,
        }))
        deps.compute_summary.side_effect = lambda rs: {"total": 3, "passed": 3, "failed": 0, "error": 0, "success_rate": 1.0}
        deps.invalidate_reports_cache.reset_mock()

        set_report_result_judgement(
            report_name="r", result_index=1, action="override",
            target_status="PASSED", reports_dir=tmp_path,
            get_report_write_lock=deps.get_report_write_lock,
            find_report=deps.find_report,
            compute_summary=deps.compute_summary,
            invalidate_reports_cache=deps.invalidate_reports_cache,
        )

        deps.compute_summary.assert_called()
        deps.invalidate_reports_cache.assert_called_once()

    def test_override_normalizes_action(self, tmp_path: Path) -> None:
        deps = MagicMock()
        deps.get_report_write_lock.return_value = MockLock()
        deps.find_report.return_value = {"meta_file": "_meta.json"}

        results = [{
            "name": "X", "status": "PASSED", "message": "ok", "method": "GET",
            "url": "http://x", "expected_status": 200,
            "item_path": [], "manual_judgement": {}, "judgement_history": [],
        }]
        _write_meta(tmp_path / "_meta.json", _make_meta(results, {
            "total": 1, "passed": 1, "failed": 0, "error": 0, "success_rate": 1.0,
        }))
        deps.compute_summary.side_effect = lambda rs: {"total": 1, "passed": 0, "failed": 1, "error": 0, "success_rate": 0.0}

        set_report_result_judgement(
            report_name="r", result_index=0, action=" OVERRIDE ",
            target_status="FAILED", reports_dir=tmp_path,
            get_report_write_lock=deps.get_report_write_lock,
            find_report=deps.find_report,
            compute_summary=deps.compute_summary,
            invalidate_reports_cache=MagicMock(),
        )
        deps.compute_summary.assert_called_once()

    def test_override_empty_target_status(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="target_status 仅支持 PASSED 或 FAILED"):
            set_report_result_judgement(
                report_name="r", result_index=0, action="override",
                target_status="", reason="",
                reports_dir=tmp_path,
                get_report_write_lock=MagicMock(),
                find_report=MagicMock(),
                compute_summary=MagicMock(),
                invalidate_reports_cache=MagicMock(),
            )

    def test_override_case_insensitive_target_status(self, tmp_path: Path) -> None:
        deps = MagicMock()
        deps.get_report_write_lock.return_value = MockLock()
        deps.find_report.return_value = {"meta_file": "_meta.json"}

        results = [{
            "name": "X", "status": "FAILED", "message": "err", "method": "GET",
            "url": "http://x", "expected_status": 200,
            "item_path": [], "manual_judgement": {}, "judgement_history": [],
        }]
        _write_meta(tmp_path / "_meta.json", _make_meta(results, {
            "total": 1, "passed": 0, "failed": 1, "error": 0, "success_rate": 0.0,
        }))
        deps.compute_summary.side_effect = lambda rs: {"total": 1, "passed": 1, "failed": 0, "error": 0, "success_rate": 1.0}

        result = set_report_result_judgement(
            report_name="r", result_index=0, action="override",
            target_status="passed", reason="", reports_dir=tmp_path,
            get_report_write_lock=deps.get_report_write_lock,
            find_report=deps.find_report,
            compute_summary=deps.compute_summary,
            invalidate_reports_cache=MagicMock(),
        )

        assert result["result"]["status"] == "PASSED"


class TestRestore:
    """restore 操作: 恢复人工判定前的原始状态."""

    def test_restore_after_override(self, tmp_path: Path) -> None:
        deps = MagicMock()
        deps.get_report_write_lock.return_value = MockLock()
        deps.find_report.return_value = {"meta_file": "_meta.json"}

        overridden = [{
            "name": "A", "folder": "", "method": "GET", "url": "http://a",
            "status": "PASSED", "message": "Overridden", "expected_status": 200,
            "item_path": [], "manual_judgement": {
                "active": True, "source": "manual", "action": "override",
                "at": "2026-06-11 10:00:00",
                "from_status": "FAILED", "from_message": "Was failing",
                "target_status": "PASSED", "reason": "It was flaky",
            },
            "judgement_history": [{"action": "override", "at": "2026-06-11 10:00:00",
                                   "from_status": "FAILED", "to_status": "PASSED", "reason": "It was flaky"}],
        }]
        _write_meta(tmp_path / "_meta.json", _make_meta(overridden, {
            "total": 1, "passed": 1, "failed": 0, "error": 0, "success_rate": 1.0,
        }))
        deps.compute_summary.side_effect = lambda rs: {"total": 1, "passed": 0, "failed": 1, "error": 0, "success_rate": 0.0}
        deps.invalidate_reports_cache.reset_mock()

        result = set_report_result_judgement(
            report_name="r", result_index=0, action="restore", reason="Auto detected again",
            reports_dir=tmp_path,
            get_report_write_lock=deps.get_report_write_lock,
            find_report=deps.find_report,
            compute_summary=deps.compute_summary,
            invalidate_reports_cache=deps.invalidate_reports_cache,
        )

        r = result["result"]
        assert r["status"] == "FAILED"
        assert r["manual_judgement"]["active"] is False
        assert r["manual_judgement"]["source"] == "auto"
        assert r["manual_judgement"]["action"] == "restore"
        assert "restored_at" in r["manual_judgement"]
        history = r["judgement_history"]
        assert any(h["action"] == "restore" for h in history)
        deps.invalidate_reports_cache.assert_called_once()

    def test_restore_preserves_from_message(self, tmp_path: Path) -> None:
        deps = MagicMock()
        deps.get_report_write_lock.return_value = MockLock()
        deps.find_report.return_value = {"meta_file": "_meta.json"}

        overridden = [{
            "name": "A", "folder": "", "method": "GET", "url": "http://a",
            "status": "PASSED", "message": "Overridden msg", "expected_status": 200,
            "item_path": [], "manual_judgement": {
                "active": True, "source": "manual", "action": "override",
                "at": "2026-06-11 10:00:00",
                "from_status": "FAILED", "from_message": "Original failure detail",
                "target_status": "PASSED", "reason": "",
            },
            "judgement_history": [],
        }]
        _write_meta(tmp_path / "_meta.json", _make_meta(overridden, {
            "total": 1, "passed": 1, "failed": 0, "error": 0, "success_rate": 1.0,
        }))
        deps.compute_summary.side_effect = lambda rs: {"total": 1, "passed": 0, "failed": 1, "error": 0, "success_rate": 0.0}

        result = set_report_result_judgement(
            report_name="r", result_index=0, action="restore",
            reports_dir=tmp_path,
            get_report_write_lock=deps.get_report_write_lock,
            find_report=deps.find_report,
            compute_summary=deps.compute_summary,
            invalidate_reports_cache=MagicMock(),
        )

        assert result["result"]["message"] == "Original failure detail"

    def test_restore_chained(self, tmp_path: Path) -> None:
        deps = MagicMock()
        deps.get_report_write_lock.return_value = MockLock()
        deps.find_report.return_value = {"meta_file": "_meta.json"}

        base_results = [{
            "name": "A", "status": "PASSED", "message": "ok", "method": "GET", "url": "http://a",
            "expected_status": 200, "item_path": [], "folder": "",
            "manual_judgement": {}, "judgement_history": [],
        }]
        _write_meta(tmp_path / "_meta.json", _make_meta(base_results, {
            "total": 1, "passed": 1, "failed": 0, "error": 0, "success_rate": 1.0,
        }))

        def step_compute(rs):
            cur = rs[0]
            mj = cur.get("manual_judgement", {})
            if isinstance(mj, dict) and mj.get("active"):
                return {"total": 1, "passed": 0, "failed": 1, "error": 0, "success_rate": 0.0}
            return {"total": 1, "passed": 1, "failed": 0, "error": 0, "success_rate": 1.0}

        deps.compute_summary.side_effect = step_compute
        deps.invalidate_reports_cache.reset_mock()

        set_report_result_judgement(
            report_name="r", result_index=0, action="override",
            target_status="FAILED", reason="first",
            reports_dir=tmp_path,
            get_report_write_lock=deps.get_report_write_lock,
            find_report=deps.find_report,
            compute_summary=deps.compute_summary,
            invalidate_reports_cache=deps.invalidate_reports_cache,
        )
        deps.invalidate_reports_cache.reset_mock()

        set_report_result_judgement(
            report_name="r", result_index=0, action="restore",
            reports_dir=tmp_path,
            get_report_write_lock=deps.get_report_write_lock,
            find_report=deps.find_report,
            compute_summary=deps.compute_summary,
            invalidate_reports_cache=deps.invalidate_reports_cache,
        )

        deps.invalidate_reports_cache.assert_called()

    def test_restore_not_active_raises(self, tmp_path: Path) -> None:
        deps = MagicMock()
        deps.get_report_write_lock.return_value = MockLock()
        deps.find_report.return_value = {"meta_file": "_meta.json"}

        no_judgement = [{
            "name": "A", "status": "PASSED", "message": "ok", "method": "GET", "url": "http://a",
            "expected_status": 200, "item_path": [], "folder": "",
            "manual_judgement": {}, "judgement_history": [],
        }]
        _write_meta(tmp_path / "_meta.json", _make_meta(no_judgement, {
            "total": 1, "passed": 1, "failed": 0, "error": 0, "success_rate": 1.0,
        }))

        with pytest.raises(ValueError, match="当前结果无可恢复的人工判定"):
            set_report_result_judgement(
                report_name="r", result_index=0, action="restore",
                reports_dir=tmp_path,
                get_report_write_lock=deps.get_report_write_lock,
                find_report=deps.find_report,
                compute_summary=MagicMock(),
                invalidate_reports_cache=MagicMock(),
            )


class TestInputValidation:
    """输入参数合法性校验."""

    def test_invalid_action_string(self) -> None:
        with pytest.raises(ValueError, match="action 仅支持 override 或 restore"):
            set_report_result_judgement(
                report_name="r", result_index=0, action="DELETE",
                reports_dir=Path("."),
                get_report_write_lock=MagicMock(),
                find_report=MagicMock(),
                compute_summary=MagicMock(),
                invalidate_reports_cache=MagicMock(),
            )

    def test_invalid_action_non_string(self) -> None:
        with pytest.raises(ValueError, match="action 仅支持 override 或 restore"):
            set_report_result_judgement(
                report_name="r", result_index=0, action=12345,
                reports_dir=Path("."),
                get_report_write_lock=MagicMock(),
                find_report=MagicMock(),
                compute_summary=MagicMock(),
                invalidate_reports_cache=MagicMock(),
            )

    def test_restore_ignores_target_status(self, tmp_path: Path) -> None:
        """restore 不校验 target_status，任意值都通过。"""
        deps = MagicMock()
        deps.get_report_write_lock.return_value = MockLock()
        deps.find_report.return_value = {"meta_file": "_meta.json"}

        overridden = [{
            "name": "A", "folder": "", "method": "GET", "url": "http://a",
            "status": "PASSED", "message": "msg", "expected_status": 200,
            "item_path": [], "manual_judgement": {
                "active": True, "source": "manual", "action": "override",
                "at": "now", "from_status": "FAILED", "from_message": "was down",
                "target_status": "PASSED", "reason": "",
            },
            "judgement_history": [],
        }]
        _write_meta(tmp_path / "_meta.json", _make_meta(overridden, {
            "total": 1, "passed": 1, "failed": 0, "error": 0, "success_rate": 1.0,
        }))
        deps.compute_summary.side_effect = lambda rs: {"total": 1, "passed": 0, "failed": 1, "error": 0, "success_rate": 0.0}

        # Should NOT raise even though target_status is invalid
        set_report_result_judgement(
            report_name="r", result_index=0, action="restore",
            target_status="GARBAGE_VALUE", reports_dir=tmp_path,
            get_report_write_lock=deps.get_report_write_lock,
            find_report=deps.find_report,
            compute_summary=deps.compute_summary,
            invalidate_reports_cache=MagicMock(),
        )

    def test_override_no_target_status(self) -> None:
        with pytest.raises(ValueError, match="target_status 仅支持 PASSED 或 FAILED"):
            set_report_result_judgement(
                report_name="r", result_index=0, action="override",
                reports_dir=Path("."),
                get_report_write_lock=MagicMock(),
                find_report=MagicMock(),
                compute_summary=MagicMock(),
                invalidate_reports_cache=MagicMock(),
            )


class TestFileErrors:
    """文件相关异常处理."""

    def test_missing_meta_file_raises(self, tmp_path: Path) -> None:
        deps = MagicMock()
        deps.get_report_write_lock.return_value = MockLock()
        deps.find_report.return_value = {"meta_file": "nonexistent_meta.json"}

        with pytest.raises(FileNotFoundError, match="元数据文件不存在"):
            set_report_result_judgement(
                report_name="r", result_index=0, action="override",
                target_status="PASSED", reports_dir=tmp_path,
                get_report_write_lock=deps.get_report_write_lock,
                find_report=deps.find_report,
                compute_summary=MagicMock(),
                invalidate_reports_cache=MagicMock(),
            )

    def test_missing_meta_file_field_raises(self) -> None:
        deps = MagicMock()
        deps.get_report_write_lock.return_value = MockLock()
        deps.find_report.return_value = {}

        with pytest.raises(ValueError, match="报告缺少 meta_file"):
            set_report_result_judgement(
                report_name="r", result_index=0, action="override",
                target_status="PASSED", reports_dir=Path("/tmp"),
                get_report_write_lock=deps.get_report_write_lock,
                find_report=deps.find_report,
                compute_summary=MagicMock(),
                invalidate_reports_cache=MagicMock(),
            )

    def test_invalid_result_index_negative(self, tmp_path: Path) -> None:
        meta_file = tmp_path / "_meta.json"
        meta_file.write_text(json.dumps({"results": [{"name": "A", "status": "PASSED"}]}), encoding="utf-8")
        deps = MagicMock()
        deps.get_report_write_lock.return_value = MockLock()
        deps.find_report.return_value = {"meta_file": "_meta.json"}

        with pytest.raises(IndexError):
            set_report_result_judgement(
                report_name="r", result_index=-1, action="override",
                target_status="PASSED", reports_dir=tmp_path,
                get_report_write_lock=deps.get_report_write_lock,
                find_report=deps.find_report,
                compute_summary=MagicMock(),
                invalidate_reports_cache=MagicMock(),
            )

    def test_result_index_out_of_range(self, tmp_path: Path) -> None:
        meta_file = tmp_path / "_meta.json"
        meta_file.write_text(json.dumps({"results": [{"name": "A", "status": "PASSED"}]}), encoding="utf-8")
        deps = MagicMock()
        deps.get_report_write_lock.return_value = MockLock()
        deps.find_report.return_value = {"meta_file": "_meta.json"}

        with pytest.raises(IndexError):
            set_report_result_judgement(
                report_name="r", result_index=999, action="override",
                target_status="PASSED", reports_dir=tmp_path,
                get_report_write_lock=deps.get_report_write_lock,
                find_report=deps.find_report,
                compute_summary=MagicMock(),
                invalidate_reports_cache=MagicMock(),
            )


class TestEdgeCases:
    """边界情况."""

    def test_empty_judgement_history_is_none(self, tmp_path: Path) -> None:
        deps = MagicMock()
        deps.get_report_write_lock.return_value = MockLock()
        deps.find_report.return_value = {"meta_file": "_meta.json"}

        results = [{
            "name": "A", "status": "FAILED", "message": "bad", "method": "GET", "url": "http://a",
            "expected_status": 200, "item_path": [], "folder": "",
            "manual_judgement": {}, "judgement_history": None,
        }]
        _write_meta(tmp_path / "_meta.json", _make_meta(results, {
            "total": 1, "passed": 0, "failed": 1, "error": 0, "success_rate": 0.0,
        }))
        deps.compute_summary.side_effect = lambda rs: {"total": 1, "passed": 1, "failed": 0, "error": 0, "success_rate": 1.0}

        result = set_report_result_judgement(
            report_name="r", result_index=0, action="override",
            target_status="PASSED", reports_dir=tmp_path,
            get_report_write_lock=deps.get_report_write_lock,
            find_report=deps.find_report,
            compute_summary=deps.compute_summary,
            invalidate_reports_cache=MagicMock(),
        )

        history = result["result"]["judgement_history"]
        assert len(history) == 1
        assert history[0]["action"] == "override"
        assert history[0]["from_status"] == "FAILED"
        assert history[0]["to_status"] == "PASSED"
        assert "at" in history[0] and isinstance(history[0]["at"], str)

    def test_judgement_history_non_list_converted(self, tmp_path: Path) -> None:
        deps = MagicMock()
        deps.get_report_write_lock.return_value = MockLock()
        deps.find_report.return_value = {"meta_file": "_meta.json"}

        results = [{
            "name": "A", "status": "FAILED", "message": "bad", "method": "GET", "url": "http://a",
            "expected_status": 200, "item_path": [], "folder": "",
            "manual_judgement": {}, "judgement_history": "old-string",
        }]
        _write_meta(tmp_path / "_meta.json", _make_meta(results, {
            "total": 1, "passed": 0, "failed": 1, "error": 0, "success_rate": 0.0,
        }))
        deps.compute_summary.side_effect = lambda rs: {"total": 1, "passed": 1, "failed": 0, "error": 0, "success_rate": 1.0}

        set_report_result_judgement(
            report_name="r", result_index=0, action="override",
            target_status="PASSED", reports_dir=tmp_path,
            get_report_write_lock=deps.get_report_write_lock,
            find_report=deps.find_report,
            compute_summary=deps.compute_summary,
            invalidate_reports_cache=MagicMock(),
        )

        deps.compute_summary.assert_called_once()

    def test_restore_with_incomplete_manual_judgement(self, tmp_path: Path) -> None:
        deps = MagicMock()
        deps.get_report_write_lock.return_value = MockLock()
        deps.find_report.return_value = {"meta_file": "_meta.json"}

        incomplete = [{
            "name": "A", "status": "PASSED", "message": "ok", "method": "GET", "url": "http://a",
            "expected_status": 200, "item_path": [], "folder": "",
            "manual_judgement": {"source": "manual"},
            "judgement_history": [],
        }]
        _write_meta(tmp_path / "_meta.json", _make_meta(incomplete, {
            "total": 1, "passed": 1, "failed": 0, "error": 0, "success_rate": 1.0,
        }))

        with pytest.raises(ValueError, match="当前结果无可恢复的人工判定"):
            set_report_result_judgement(
                report_name="r", result_index=0, action="restore",
                reports_dir=tmp_path,
                get_report_write_lock=deps.get_report_write_lock,
                find_report=deps.find_report,
                compute_summary=MagicMock(),
                invalidate_reports_cache=MagicMock(),
            )

    def test_action_none_defaults_to_override(self, tmp_path: Path) -> None:
        deps = MagicMock()
        deps.get_report_write_lock.return_value = MockLock()
        deps.find_report.return_value = {"meta_file": "_meta.json"}

        results = [{
            "name": "A", "status": "FAILED", "message": "err", "method": "GET", "url": "http://a",
            "expected_status": 200, "item_path": [], "folder": "",
            "manual_judgement": {}, "judgement_history": [],
        }]
        _write_meta(tmp_path / "_meta.json", _make_meta(results, {
            "total": 1, "passed": 0, "failed": 1, "error": 0, "success_rate": 0.0,
        }))
        deps.compute_summary.side_effect = lambda rs: {"total": 1, "passed": 1, "failed": 0, "error": 0, "success_rate": 1.0}

        result = set_report_result_judgement(
            report_name="r", result_index=0, action=None,
            target_status="PASSED", reports_dir=tmp_path,
            get_report_write_lock=deps.get_report_write_lock,
            find_report=deps.find_report,
            compute_summary=deps.compute_summary,
            invalidate_reports_cache=MagicMock(),
        )

        assert result["result"]["status"] == "PASSED"
        assert result["result"]["manual_judgement"]["active"] is True

    def test_return_values_are_complete(self, tmp_path: Path) -> None:
        deps = MagicMock()
        deps.get_report_write_lock.return_value = MockLock()
        deps.find_report.return_value = {"meta_file": "_meta.json"}

        results = [{
            "name": "A", "status": "FAILED", "message": "err", "method": "GET", "url": "http://a",
            "expected_status": 200, "item_path": [], "folder": "",
            "manual_judgement": {}, "judgement_history": [],
        }]
        expected_stats = {"total": 1, "passed": 1, "failed": 0, "error": 0, "success_rate": 1.0}
        _write_meta(tmp_path / "_meta.json", _make_meta(results, {
            "total": 1, "passed": 0, "failed": 1, "error": 0, "success_rate": 0.0,
        }))
        deps.compute_summary.side_effect = lambda rs: expected_stats

        result = set_report_result_judgement(
            report_name="r", result_index=0, action="override",
            target_status="PASSED", reports_dir=tmp_path,
            get_report_write_lock=deps.get_report_write_lock,
            find_report=deps.find_report,
            compute_summary=deps.compute_summary,
            invalidate_reports_cache=MagicMock(),
        )

        assert isinstance(result, dict)
        assert "summary" in result
        assert "result" in result
        assert result["summary"]["total"] == expected_stats["total"]
        assert result["summary"]["passed"] == expected_stats["passed"]
        assert result["summary"]["failed"] == expected_stats["failed"]
        assert result["summary"]["error"] == expected_stats["error"]
        assert result["summary"]["success_rate"] == expected_stats["success_rate"]
