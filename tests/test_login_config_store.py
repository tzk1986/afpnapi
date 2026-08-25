"""登录配置存储服务单元测试。"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from postman_api_tester.services.ui_login_config_store import (
    UiLoginConfigStore,
)


class TestUiLoginConfigStore(unittest.TestCase):
    """登录配置存储测试。"""

    def setUp(self) -> None:
        self._tmp = Path(tempfile.mkdtemp())
        self.store = UiLoginConfigStore(configs_dir=self._tmp)

    def tearDown(self) -> None:
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_save_and_get(self) -> None:
        config = {
            "name": "管理员登录",
            "base_url": "http://example.com",
            "login_steps": [
                {"action": "navigate", "value": "/login"},
                {"action": "type", "selector": "#user", "value": "admin"},
            ],
            "success_condition": {"type": "url_pattern", "value": "/dashboard"},
        }
        config_id = self.store.save_config(config)
        self.assertTrue(config_id.startswith("login_"))

        loaded = self.store.get_config(config_id)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["name"], "管理员登录")
        self.assertEqual(loaded["base_url"], "http://example.com")
        self.assertEqual(len(loaded["login_steps"]), 2)
        self.assertEqual(loaded["success_condition"]["type"], "url_pattern")
        self.assertIn("created_at", loaded)
        self.assertIn("updated_at", loaded)

    def test_get_nonexistent(self) -> None:
        self.assertIsNone(self.store.get_config("login_nonexistent"))

    def test_list_configs(self) -> None:
        for i in range(3):
            self.store.save_config(
                {"name": f"配置{i}", "base_url": f"http://example{i}.com"}
            )

        configs = self.store.list_configs()
        self.assertEqual(len(configs), 3)
        # 摘要不含完整步骤
        for c in configs:
            self.assertIn("id", c)
            self.assertIn("name", c)
            self.assertIn("step_count", c)

    def test_delete_config(self) -> None:
        config_id = self.store.save_config(
            {"name": "临时", "base_url": "http://example.com"}
        )
        self.assertTrue(self.store.delete_config(config_id))
        self.assertIsNone(self.store.get_config(config_id))
        # 重复删除
        self.assertFalse(self.store.delete_config(config_id))

    def test_find_by_base_url(self) -> None:
        self.store.save_config(
            {"name": "系统A", "base_url": "http://10.0.0.1:8080"}
        )
        self.store.save_config(
            {"name": "系统B", "base_url": "http://10.0.0.2:9090"}
        )

        found = self.store.find_by_base_url("http://10.0.0.1:8080")
        self.assertIsNotNone(found)
        self.assertEqual(found["name"], "系统A")

        self.assertIsNone(self.store.find_by_base_url("http://unknown.com"))

    def test_save_preserves_created_at(self) -> None:
        config_id = self.store.save_config(
            {"name": "原版", "base_url": "http://example.com"}
        )
        original = self.store.get_config(config_id)
        assert original is not None
        created_at = original["created_at"]

        # 更新
        self.store.save_config({**original, "name": "更新版"})
        updated = self.store.get_config(config_id)
        assert updated is not None
        self.assertEqual(updated["name"], "更新版")
        self.assertEqual(updated["created_at"], created_at)

    def test_corrupted_file_skipped(self) -> None:
        bad_file = self._tmp / "login_bad.json"
        bad_file.write_text("not json", encoding="utf-8")

        self.assertIsNone(self.store.get_config("login_bad"))
        configs = self.store.list_configs()
        self.assertEqual(len(configs), 0)

    def test_empty_steps_and_condition(self) -> None:
        config_id = self.store.save_config(
            {"name": "空配置", "base_url": "http://example.com"}
        )
        loaded = self.store.get_config(config_id)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["login_steps"], [])
        self.assertEqual(loaded["success_condition"], {})


if __name__ == "__main__":
    unittest.main()
