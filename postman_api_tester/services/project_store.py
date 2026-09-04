"""项目脚手架文件存储服务（v1.39.0，功能默认关闭）。

开发导读:
- 职责：project.json 与项目目录内相对文件（collections/tracing/docs）的线程安全读写；
  模板两源（包内 builtin + 仓库根 user）合并读取，同名以 user 覆盖 builtin。
- 本层只做"id 白名单校验 + 路径守卫 + 锁 + 原子写 + 目录懒建"，
  schema 校验、占位符渲染、CAS、统计等业务规则在 project_service.py。
- 懒建目录（G-25）：构造对象不触碰文件系统，仅首次写入时 mkdir，
  保证 ENABLE_PROJECT_SCAFFOLD=false 时 import 零文件系统痕迹。
- 提交标记（G-17）：project.json 是创建流程最后写入的文件；
  目录内无 project.json 即视为未提交垃圾，list 跳过但不删除（保守策略）。
- 四重防护（v2 冲突 3）：id 正则 → 拼接后 resolve().is_relative_to 守卫 →
  project.json 存在性 → 才允许 rmtree。
"""

import json
import logging
import re
import shutil
import threading
import time
import uuid
from pathlib import Path
from contextlib import AbstractContextManager
from typing import Any, Callable, Dict, List, Optional, Tuple

from postman_api_tester.config import (
    PROJECT_BUILTIN_TEMPLATES_DIR,
    PROJECT_TEMPLATES_DIR,
    PROJECTS_DIR,
)
from postman_api_tester.utils.file_utils import atomic_write_json

logger = logging.getLogger(__name__)

# id 白名单（G-18）：封闭字符集，天然排除 ../、%2e、中文、盘符、超长
PROJECT_ID_RE = re.compile(r"^proj_[a-z0-9]{12}$")
TEMPLATE_ID_RE = re.compile(r"^tpl_[a-z0-9_]{2,32}$")

PROJECT_FILE_NAME = "project.json"


def _atomic_write_json(path: Path, data: Any) -> None:
    """Windows 下杀软/索引器句柄可偶发阻挡 replace，退避重试数次再上抛。"""
    for attempt in range(4):
        try:
            atomic_write_json(path, data)
            return
        except PermissionError:
            if attempt == 3:
                raise
            time.sleep(0.05 * (attempt + 1))


class ProjectStore:
    """项目主数据存储：projects/<proj_id>/project.json + 目录内相对文件。"""

    def __init__(self, projects_dir: Optional[Path] = None) -> None:
        self._dir = Path(projects_dir) if projects_dir is not None else PROJECTS_DIR
        # RLock：服务层可在 with store.exclusive() 内组合调用各读写方法（G-30 懒对账）
        self._lock = threading.RLock()

    # ---------- id 与路径 ----------

    @staticmethod
    def is_valid_project_id(project_id: str) -> bool:
        return bool(PROJECT_ID_RE.fullmatch(str(project_id or "")))

    @staticmethod
    def generate_project_id() -> str:
        return f"proj_{uuid.uuid4().hex[:12]}"

    def project_dir(self, project_id: str) -> Path:
        """返回守卫后的项目目录（不创建）。id 非法抛 ValueError。"""
        if not self.is_valid_project_id(project_id):
            raise ValueError(f"非法项目 id: {project_id!r}")
        base = self._dir.resolve()
        candidate = (base / project_id).resolve()
        if not candidate.is_relative_to(base):
            raise ValueError(f"项目目录穿越拒绝: {project_id!r}")
        return candidate

    def resolve_project_path(self, project_id: str, rel_path: str) -> Path:
        """项目目录内相对路径的安全解析（G-32 使用期校验）。

        拒绝空串、绝对路径、盘符、UNC 及一切 resolve 后越界；非法抛 ValueError。
        """
        proj_dir = self.project_dir(project_id)
        raw = str(rel_path or "").strip()
        if not raw:
            raise ValueError("项目相对路径为空")
        if raw.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", raw):
            raise ValueError(f"项目相对路径不得为绝对路径: {rel_path!r}")
        candidate = (proj_dir / raw).resolve()
        if not candidate.is_relative_to(proj_dir):
            raise ValueError(f"项目相对路径穿越拒绝: {rel_path!r}")
        return candidate

    def project_json_path(self, project_id: str) -> Path:
        return self.resolve_project_path(project_id, PROJECT_FILE_NAME)

    def is_committed(self, project_id: str) -> bool:
        """提交标记：project.json 是否落盘。"""
        try:
            return self.project_json_path(project_id).is_file()
        except ValueError:
            return False

    # ---------- project.json CRUD ----------

    def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        try:
            path = self.project_json_path(project_id)
        except ValueError:
            return None
        with self._lock:
            if not path.is_file():
                return None
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("读取 project.json 失败 %s: %s", path, exc)
                return None
        return data if isinstance(data, dict) else None

    def save_project(self, project: Dict[str, Any]) -> Path:
        """原子写 project.json（提交标记；目录懒建发生在这里）。"""
        project_id = str(project.get("id") or "")
        path = self.project_json_path(project_id)
        with self._lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            _atomic_write_json(path, project)
        return path

    def exclusive(self) -> AbstractContextManager[bool]:
        """暴露排他锁供服务层组合原子读改写（G-30 懒对账 / G-36 CAS 共用）。"""
        return self._lock

    def update_project(
        self,
        project_id: str,
        mutator: Callable[[Dict[str, Any]], Optional[Dict[str, Any]]],
    ) -> Optional[Dict[str, Any]]:
        """锁内 read-modify-write。mutator 返回 None 表示放弃本次写。"""
        with self._lock:
            data = self.get_project(project_id)
            if data is None:
                return None
            result = mutator(data)
            if result is None:
                return None
            self.save_project(result)
            return result

    def list_projects(self) -> List[Dict[str, Any]]:
        """扫描两重过滤：目录名匹配 id 正则 + project.json 存在且可解析。

        未提交/损坏目录跳过不删（G-17 保守策略）。按目录 mtime 新→旧排序。
        """
        base = self._dir
        if not base.is_dir():
            return []
        result: List[Dict[str, Any]] = []
        with self._lock:
            for child in sorted(base.glob("proj_*"), key=_mtime_of, reverse=True):
                if not child.is_dir():
                    continue
                if not self.is_valid_project_id(child.name):
                    continue
                json_path = child / PROJECT_FILE_NAME
                if not json_path.is_file():
                    continue  # 未提交垃圾目录：跳过
                try:
                    data = json.loads(json_path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError) as exc:
                    logger.warning("扫描 project.json 失败 %s: %s", json_path, exc)
                    continue
                if isinstance(data, dict):
                    result.append(data)
        return result

    def delete_project(self, project_id: str) -> bool:
        """删除已提交项目（四重防护）；不存在/未提交返回 False。"""
        try:
            proj_dir = self.project_dir(project_id)
        except ValueError:
            return False
        with self._lock:
            if not (proj_dir / PROJECT_FILE_NAME).is_file():
                return False
            base = self._dir.resolve()
            resolved = proj_dir.resolve()
            if not resolved.is_relative_to(base) or resolved == base:
                raise ValueError(f"删除目标越界拒绝: {project_id!r}")
            shutil.rmtree(resolved)
        logger.info("已删除项目目录: %s", project_id)
        return True

    # ---------- 创建流程：目录准备与回滚（G-17/G-18） ----------

    def prepare_new_project_dir(self, project_id: str) -> Path:
        """为新项目建目录；id 已占用抛 FileExistsError（service 层重试一次）。"""
        proj_dir = self.project_dir(project_id)
        proj_dir.mkdir(parents=True, exist_ok=False)
        return proj_dir

    def rollback_project_dir(self, project_id: str) -> None:
        """创建中途失败的守卫式回滚：仅删本 store 管理、位于 projects 根内的目录。"""
        try:
            proj_dir = self.project_dir(project_id)
        except ValueError:
            return
        base = self._dir.resolve()
        resolved = proj_dir.resolve()
        if resolved != base and resolved.is_relative_to(base) and resolved.is_dir():
            shutil.rmtree(resolved, ignore_errors=True)
            logger.info("创建回滚：已清理半成品目录 %s", project_id)

    # ---------- 项目目录内相对文件（collections / tracing / docs） ----------

    def read_project_json(self, project_id: str, rel_path: str) -> Optional[Any]:
        path = self.resolve_project_path(project_id, rel_path)
        with self._lock:
            if not path.is_file():
                return None
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("读取 %s 失败: %s", path, exc)
                return None

    def write_project_json(self, project_id: str, rel_path: str, data: Any) -> Path:
        path = self.resolve_project_path(project_id, rel_path)
        with self._lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            _atomic_write_json(path, data)
        return path

    def write_project_text(self, project_id: str, rel_path: str, content: str) -> Path:
        """docs 等非 JSON 生成物（files manifest 渲染结果）。"""
        path = self.resolve_project_path(project_id, rel_path)
        with self._lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        return path

    def delete_project_file(self, project_id: str, rel_path: str) -> bool:
        path = self.resolve_project_path(project_id, rel_path)
        with self._lock:
            if not path.is_file():
                return False
            path.unlink()
        return True


class ProjectTemplateStore:
    """模板两源存储：builtin（包内只读，随代码分发）+ user（可写，gitignore）。

    磁盘布局（v5 一节定稿）：`<root>/<目录名>/template.json`；
    内置模板目录名为短名（api_basic 等），模板 id 以文件内容 `id` 字段为权威
    （格式 `^tpl_[a-z0-9_]{2,32}$`）。用户模板以 id 作目录名写入 user 根。
    合并规则（v3 4.1 定稿）：同名 id 以 user 覆盖 builtin，附 source 字段。
    """

    TEMPLATE_FILE_NAME = "template.json"

    def __init__(
        self,
        builtin_dir: Optional[Path] = None,
        user_dir: Optional[Path] = None,
    ) -> None:
        self._builtin = (
            Path(builtin_dir)
            if builtin_dir is not None
            else PROJECT_BUILTIN_TEMPLATES_DIR
        )
        self._user = Path(user_dir) if user_dir is not None else PROJECT_TEMPLATES_DIR
        self._lock = threading.RLock()

    @staticmethod
    def is_valid_template_id(template_id: str) -> bool:
        return bool(TEMPLATE_ID_RE.fullmatch(str(template_id or "")))

    def _user_template_path(self, template_id: str) -> Path:
        """用户模板写入路径：id 即目录名，正则白名单已排除一切穿越字符。"""
        if not self.is_valid_template_id(template_id):
            raise ValueError(f"非法模板 id: {template_id!r}")
        base = self._user.resolve()
        candidate = (base / template_id / self.TEMPLATE_FILE_NAME).resolve()
        if not candidate.is_relative_to(base):
            raise ValueError(f"模板路径穿越拒绝: {template_id!r}")
        return candidate

    def _scan_source(self, base: Path, source: str) -> Dict[str, Dict[str, Any]]:
        """扫描单源全部模板；id 非法/损坏条目跳过（记日志），返回 id→对象。"""
        found: Dict[str, Dict[str, Any]] = {}
        if not base.is_dir():
            return found
        for tpl_path in sorted(base.glob(f"*/{self.TEMPLATE_FILE_NAME}")):
            try:
                data = json.loads(tpl_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("扫描模板失败 %s: %s", tpl_path, exc)
                continue
            if not isinstance(data, dict):
                continue
            tid = str(data.get("id") or "")
            if not self.is_valid_template_id(tid):
                logger.warning("模板 id 非法，跳过: %s (%s)", tpl_path, tid)
                continue
            data["source"] = source
            found[tid] = data
        return found

    def get_template(self, template_id: str) -> Optional[Dict[str, Any]]:
        """按 id 取模板（合并两源，user 覆盖 builtin），附 source 标记。"""
        if not self.is_valid_template_id(template_id):
            return None
        with self._lock:
            merged = self._scan_source(self._user, "user")
            if template_id not in merged:
                merged.update(self._scan_source(self._builtin, "builtin"))
            return merged.get(template_id)

    def list_templates(self) -> List[Dict[str, Any]]:
        """两源合并列表；同名 id user 覆盖 builtin；按 id 排序。"""
        with self._lock:
            merged = self._scan_source(self._builtin, "builtin")
            merged.update(self._scan_source(self._user, "user"))
            return [merged[key] for key in sorted(merged)]

    def template_exists(self, template_id: str) -> bool:
        return self.get_template(template_id) is not None

    def builtin_template_exists(self, template_id: str) -> bool:
        """内置源是否已有同 id 模板（A15 TPL_002 只读拒绝依据）。"""
        if not self.is_valid_template_id(template_id):
            return False
        with self._lock:
            return template_id in self._scan_source(self._builtin, "builtin")

    def user_template_path_exists(self, template_id: str) -> bool:
        if not self.is_valid_template_id(template_id):
            return False
        return self._user_template_path(template_id).is_file()

    def save_user_template(self, template: Dict[str, Any]) -> Path:
        """写用户模板（原子写；user 目录懒建发生在这里）。"""
        template_id = str(template.get("id") or "")
        path = self._user_template_path(template_id)
        with self._lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            _atomic_write_json(path, template)
        logger.info("已保存用户模板: %s", template_id)
        return path

    def delete_user_template(self, template_id: str) -> bool:
        """A16：整目录删除用户模板；不存在返回 False。id 已经正则白名单守卫。"""
        path = self._user_template_path(template_id)
        with self._lock:
            target = path.parent
            if not target.is_dir():
                return False
            shutil.rmtree(target)
        logger.info("已删除用户模板: %s", template_id)
        return True


def _mtime_of(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0
