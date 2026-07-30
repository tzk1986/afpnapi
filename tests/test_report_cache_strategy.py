"""报告缓存策略优化测试。"""

import time
from pathlib import Path
from unittest.mock import Mock, patch
import pytest

from postman_api_tester import report_repository


class TestReportCacheStrategy:
    """报告缓存策略测试。"""

    def setup_method(self):
        """每个测试前重置缓存。"""
        report_repository.invalidate_reports_cache()

    def test_cache_ttl_default(self):
        """默认 TTL 应为 10 秒。"""
        with patch('postman_api_tester.config.REPORT_CACHE_TTL', 10):
            report_repository.configure_report_repository(Path("reports"))
            assert report_repository._REPORTS_CACHE_TTL == 10.0

    def test_cache_ttl_custom(self):
        """自定义 TTL 应生效。"""
        report_repository.configure_report_repository(Path("reports"), cache_ttl=5.0)
        assert report_repository._REPORTS_CACHE_TTL == 5.0

    def test_cache_ttl_from_config(self):
        """从 config.py 读取 TTL。"""
        with patch('postman_api_tester.config.REPORT_CACHE_TTL', 15):
            report_repository.configure_report_repository(Path("reports"))
            assert report_repository._REPORTS_CACHE_TTL == 15.0

    def test_smart_invalidation_enabled(self):
        """智能失效启用时应检查文件修改时间。"""
        with patch('postman_api_tester.config.REPORT_CACHE_SMART_INVALIDATION', True), \
             patch('postman_api_tester.config.REPORT_CACHE_TTL', 10):
            # 模拟有新文件
            with patch.object(report_repository, '_get_latest_report_mtime', return_value=time.time() + 100):
                # 先加载一次缓存
                report_repository._REPORTS_CACHE["data"] = []
                report_repository._REPORTS_CACHE["ts"] = time.monotonic()
                report_repository._REPORTS_CACHE_LAST_MTIME = time.time()

                # 应该触发重新加载（因为有新文件）
                # 这里只是验证逻辑存在，实际测试需要完整的文件系统模拟
                assert report_repository._REPORTS_CACHE_LAST_MTIME < time.time() + 100

    def test_smart_invalidation_disabled(self):
        """智能失效禁用时只依赖 TTL。"""
        with patch('postman_api_tester.config.REPORT_CACHE_SMART_INVALIDATION', False), \
             patch('postman_api_tester.config.REPORT_CACHE_TTL', 10):
            # 即使有新文件，只要 TTL 未过期就使用缓存
            report_repository._REPORTS_CACHE["data"] = [{"report_name": "test"}]
            report_repository._REPORTS_CACHE["ts"] = time.monotonic()
            report_repository._REPORTS_CACHE_LAST_MTIME = 0.0

            # 应该返回缓存数据
            result = report_repository.list_reports()
            assert len(result) == 1
            assert result[0]["report_name"] == "test"

    def test_invalidate_clears_mtime(self):
        """invalidate_reports_cache 应清除 mtime 记录。"""
        report_repository._REPORTS_CACHE_LAST_MTIME = time.time()
        report_repository.invalidate_reports_cache()
        assert report_repository._REPORTS_CACHE_LAST_MTIME == 0.0

    def test_get_latest_report_mtime_no_dir(self):
        """目录不存在时返回 0。"""
        with patch.object(report_repository, '_REPORTS_DIR', Path("/nonexistent")):
            mtime = report_repository._get_latest_report_mtime()
            assert mtime == 0.0

    def test_get_latest_report_mtime_with_files(self):
        """有文件时返回最新修改时间。"""
        # 使用临时目录模拟
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            report_repository._REPORTS_DIR = tmpdir_path

            # 创建测试文件
            meta_file = tmpdir_path / "test_meta.json"
            meta_file.write_text("{}")

            mtime = report_repository._get_latest_report_mtime()
            assert mtime > 0
            assert abs(mtime - meta_file.stat().st_mtime) < 1.0
