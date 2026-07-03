"""UI 测试用例文件存储服务。

以 JSON 文件形式持久化存储 UI 自动化测试用例，
提供 CRUD 操作和线程安全的文件访问。
"""

import json
import logging
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_DEFAULT_CASES_DIR = Path("ui_testing_cases")


class UiCaseStore:
    """UI 测试用例 JSON 文件存储。"""

    def __init__(self, cases_dir: Optional[Path] = None) -> None:
        self._cases_dir = cases_dir or _DEFAULT_CASES_DIR
        self._lock = threading.Lock()
        self._cases_dir.mkdir(parents=True, exist_ok=True)

    def create_case(self, case: Dict[str, Any]) -> str:
        """创建用例，返回 case_id。"""
        case_id = case.get("id") or str(uuid.uuid4())[:12]
        now = datetime.now().isoformat()

        record: Dict[str, Any] = {
            "id": case_id,
            "name": case.get("name", "未命名用例"),
            "description": case.get("description", ""),
            "base_url": case.get("base_url", ""),
            "steps": case.get("steps", []),
            "assertions": case.get("assertions", []),
            "variables": case.get("variables", {}),
            "tags": case.get("tags", []),
            "created_at": now,
            "updated_at": now,
        }

        file_path = self._cases_dir / f"case_{case_id}.json"
        with self._lock:
            file_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

        logger.info("Created UI test case: %s", case_id)
        return case_id

    def list_cases(self) -> List[Dict[str, Any]]:
        """列出所有用例（不含完整 steps，只返回摘要）。"""
        result: List[Dict[str, Any]] = []
        with self._lock:
            for file_path in sorted(self._cases_dir.glob("case_*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
                try:
                    data = json.loads(file_path.read_text(encoding="utf-8"))
                    result.append({
                        "id": data.get("id", ""),
                        "name": data.get("name", ""),
                        "description": data.get("description", ""),
                        "base_url": data.get("base_url", ""),
                        "step_count": len(data.get("steps", [])),
                        "tags": data.get("tags", []),
                        "created_at": data.get("created_at", ""),
                        "updated_at": data.get("updated_at", ""),
                    })
                except (json.JSONDecodeError, OSError) as e:
                    logger.warning("Failed to read case file %s: %s", file_path, e)

        return result

    def get_case(self, case_id: str) -> Optional[Dict[str, Any]]:
        """获取用例完整数据。"""
        file_path = self._cases_dir / f"case_{case_id}.json"
        with self._lock:
            if not file_path.exists():
                return None
            try:
                return json.loads(file_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                logger.error("Failed to read case %s: %s", case_id, e)
                return None

    def update_case(self, case_id: str, updates: Dict[str, Any]) -> bool:
        """更新用例。"""
        file_path = self._cases_dir / f"case_{case_id}.json"
        with self._lock:
            if not file_path.exists():
                return False
            try:
                data = json.loads(file_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return False

            for key in ("name", "description", "base_url", "steps", "assertions", "variables", "tags"):
                if key in updates:
                    data[key] = updates[key]

            data["updated_at"] = datetime.now().isoformat()
            file_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

        logger.info("Updated UI test case: %s", case_id)
        return True

    def delete_case(self, case_id: str) -> bool:
        """删除用例。"""
        file_path = self._cases_dir / f"case_{case_id}.json"
        with self._lock:
            if not file_path.exists():
                return False
            file_path.unlink()
        logger.info("Deleted UI test case: %s", case_id)
        return True
