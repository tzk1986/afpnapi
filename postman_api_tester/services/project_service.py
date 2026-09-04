"""项目脚手架领域服务（v1.39.0，功能默认关闭）。

开发导读:
- 职责：A1~A8/A10~A11/A14~A15 的业务编排——schema 驱动校验（G-31）、受限占位符
  替换（G-20，禁 Jinja2）、files manifest 声明式生成引擎（G-32/G-33 双期校验）、
  A4/A11 乐观锁 CAS（G-36，A4 冲突码 PRJ_306）、执行历史"入队即记录 +
  查询时懒对账"状态机（G-30）、创建失败带守卫回滚（G-17）、history cap=20（G-23）、
  secret answers 落盘脱敏（R15）。
- 错误以 ProjectError(code, message, http_status) 抛出，由 project_routes 统一
  转 json_error 包装；一码一义见 v3 5.4 与本文映射（PRJ_302 并入 PRJ_102）。
- A9 执行入队（S3.1）：execute_project 合并集合为临时文件
  （uploaded_collections/<job_id>.json，复用 build_saved_json_path），
  与手工执行同队列（v2 R3），入队后调 record_execution_enqueued 记录；
  统计收敛依赖 reconcile_executions 查询时懒对账（G-30）。
- 只读 import report_job_store / report_repository（真值优先级：报告>内存>unknown），
  不触碰其生命周期（R13）。
"""

import json
import logging
import re
import uuid
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from postman_api_tester.config import (
    PROJECT_EXECUTION_HISTORY_MAX,
    PROJECT_LIST_PAGE_SIZE_DEFAULT,
    PROJECT_MAX_COLLECTIONS,
    PROJECT_TEMPLATE_MAX_BYTES,
)
from postman_api_tester.report_job_store import get_run_job, set_run_job
from postman_api_tester.report_repository import find_report, invalidate_reports_cache
from postman_api_tester.report_server_config import (
    ENVIRONMENTS,
    RUN_RESULTS_PER_PAGE_DEFAULT,
)
from postman_api_tester.services.project_store import (
    ProjectStore,
    ProjectTemplateStore,
)
from postman_api_tester.services.report_job_execution_service import (
    enqueue_job_with_worker,
    run_postman_job,
)
from postman_api_tester.services.report_job_submission_service import (
    build_run_postman_job_params,
    build_saved_json_path,
    save_collection_json,
)
from postman_api_tester.services.report_request_service import is_valid_http_url
from postman_api_tester.utils.server_utils import clamp_page, clamp_page_size

logger = logging.getLogger(__name__)

# 与 handlers/job_routes.py 同路径规则（禁 import handlers，允许常量镜像）
UPLOADS_DIR = (Path(__file__).resolve().parent.parent / "uploaded_collections").resolve()

_RUN_POSTMAN_JOB_FN = partial(
    run_postman_job,
    set_run_job=set_run_job,
    invalidate_reports_cache=invalidate_reports_cache,
)

SCHEMA_VERSION = 1
PROJECT_STATUSES = ("active", "completed", "archived")
TRACING_CONVERT_STATUSES = ("pending", "automated", "manual")
VARIABLE_TYPES = ("enum", "bool", "string", "secret")
PENDING_HISTORY_STATUSES = ("queued", "running")

# 受限占位符（G-20）：仅 {{key}} 键替换，绝不进 Jinja2
_PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Za-z][A-Za-z0-9_]{0,63})\s*\}\}")
_VAR_KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,31}$")
_WIN_RESERVED = (
    {"con", "prn", "aux", "nul"}
    | {f"com{i}" for i in range(1, 10)}
    | {f"lpt{i}" for i in range(1, 10)}
)
_PATH_SEG_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_\-. ]{0,63}$")


class ProjectError(Exception):
    """脚手架业务错误：routes 层捕获后转 BaseHandler.json_error。"""

    def __init__(
        self,
        code: str,
        message: str,
        http_status: int = 400,
        data: Any = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.data = data


def _now_iso() -> str:
    return datetime.now().isoformat()


def validate_manifest_path(rel_path: str) -> str:
    """files.path 白名单校验（G-32/G-33 双期共用）：相对、分段安全、禁保留名。

    非法抛 ValueError（A15 声明期转 TPL_001，创建使用期转 PRJ_203）。
    """
    raw = str(rel_path or "").strip().replace("\\", "/")
    if not raw:
        raise ValueError("files.path 为空")
    if raw.startswith("/") or re.match(r"^[A-Za-z]:", raw):
        raise ValueError(f"files.path 不得为绝对路径/盘符: {rel_path!r}")
    for part in raw.split("/"):
        if part in ("", ".", ".."):
            raise ValueError(f"files.path 含非法分段: {rel_path!r}")
        if not _PATH_SEG_RE.match(part):
            raise ValueError(f"files.path 分段字符非法: {part!r}")
        if part.split(".")[0].lower() in _WIN_RESERVED:
            raise ValueError(f"files.path 含 Windows 保留名: {part!r}")
    return raw


def _count_requests(items: Any) -> int:
    total = 0
    if isinstance(items, list):
        for it in items:
            if not isinstance(it, dict):
                continue
            if "request" in it:
                total += 1
            total += _count_requests(it.get("item"))
    return total


def _norm_value_for_render(value: Any) -> Optional[str]:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return None
    if isinstance(value, (str, int, float)):
        return str(value)
    return None


class ProjectService:
    """脚手架业务编排；store 可注入（单测隔离），默认为包级 config 目录。"""

    def __init__(
        self,
        project_store: Optional[ProjectStore] = None,
        template_store: Optional[ProjectTemplateStore] = None,
    ) -> None:
        self.store = project_store or ProjectStore()
        self.templates = template_store or ProjectTemplateStore()

    # ================= 模板（A14/A15 + 两源合并） =================

    def load_template_merged(self, template_id: str) -> Dict[str, Any]:
        """取模板（user 覆盖 builtin）并做使用期声明校验；不存在 PRJ_203。"""
        tpl = self.templates.get_template(template_id)
        if tpl is None:
            raise ProjectError("PRJ_203", f"模板不存在: {template_id}", 404)
        try:
            self._validate_template_declaration(tpl)
        except ValueError as exc:
            raise ProjectError("PRJ_203", f"模板声明非法: {exc}", 404)
        return tpl

    def list_templates(self) -> Dict[str, Any]:
        items = [
            {
                "id": t.get("id"),
                "name": t.get("name", ""),
                "description": t.get("description", ""),
                "version": t.get("version", "1.0.0"),
                "source": t.get("source", "builtin"),
                "variables": t.get("variables", []),
            }
            for t in self.templates.list_templates()
        ]
        return {"items": items}

    def create_template(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """A15：服务端重写 id/author/created_at（G-33），声明期全量校验。"""
        if not isinstance(payload, dict):
            raise ProjectError("TPL_001", "模板请求体必须为 JSON 对象")
        try:
            size = len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        except (TypeError, ValueError) as exc:
            raise ProjectError("TPL_001", f"模板不是合法 JSON: {exc}")
        if size > PROJECT_TEMPLATE_MAX_BYTES:
            raise ProjectError(
                "TPL_001",
                f"模板体积 {size}B 超过上限 {PROJECT_TEMPLATE_MAX_BYTES}B",
            )
        name = str(payload.get("name") or "").strip()
        if not name:
            raise ProjectError("TPL_001", "模板名称不能为空")

        template_id = self._derive_user_template_id(name)
        if self.templates.builtin_template_exists(template_id):
            raise ProjectError(
                "TPL_002", f"与内置模板同 id，内置模板只读: {template_id}", 409
            )

        try:
            template: Dict[str, Any] = {
                "schema_version": SCHEMA_VERSION,
                "id": template_id,
                "name": name,
                "description": str(payload.get("description") or "").strip(),
                "version": str(payload.get("version") or "1.0.0").strip(),
                "author": str(payload.get("author") or "").strip(),
                "created_at": _now_iso(),
                "metadata_template": self._clean_metadata_template(
                    payload.get("metadata_template")
                ),
                "variables": self._clean_variables(payload.get("variables")),
                "files": self._clean_files(payload.get("files")),
            }
            self._validate_template_declaration(template)
            path = self.templates.save_user_template(template)
        except ProjectError:
            raise
        except ValueError as exc:
            raise ProjectError("TPL_001", f"模板声明非法: {exc}")
        except OSError as exc:
            logger.error("模板写入失败 %s: %s", template_id, exc)
            raise ProjectError("TPL_003", "模板创建失败", 500)
        template["source"] = "user"
        logger.info("已创建用户模板: %s -> %s", template_id, path)
        return template

    def _derive_user_template_id(self, name: str) -> str:
        slug = re.sub(r"[^a-z0-9_]", "_", name.lower()).strip("_")
        slug = re.sub(r"_+", "_", slug)[:28].strip("_")
        if len(slug) >= 2:
            candidate = f"tpl_{slug}"
            if not self.templates.user_template_path_exists(candidate):
                return candidate
        return f"tpl_{uuid.uuid4().hex[:12]}"

    def _clean_metadata_template(
        self, raw: Any
    ) -> Dict[str, str]:
        if raw in (None, {}):
            return {}
        if not isinstance(raw, dict):
            raise ValueError("metadata_template 必须为对象")
        cleaned: Dict[str, str] = {}
        for key, value in raw.items():
            k = str(key)
            if not _VAR_KEY_RE.match(k):
                raise ValueError(f"metadata_template 键非法: {k!r}")
            cleaned[k] = str(value)
        return cleaned

    def _clean_variables(self, raw: Any) -> List[Dict[str, Any]]:
        if raw in (None, []):
            return []
        if not isinstance(raw, list):
            raise ValueError("variables 必须为数组")
        seen: Set[str] = set()
        cleaned: List[Dict[str, Any]] = []
        for item in raw:
            if not isinstance(item, dict):
                raise ValueError("variables 元素必须为对象")
            key = str(item.get("key") or "").strip()
            if not _VAR_KEY_RE.match(key):
                raise ValueError(f"变量 key 非法: {key!r}")
            if key in seen:
                raise ValueError(f"变量 key 重复: {key!r}")
            seen.add(key)
            vtype = str(item.get("type") or "string").strip().lower()
            if vtype not in VARIABLE_TYPES:
                raise ValueError(f"变量 type 非法: {vtype!r}")
            options = item.get("options") or []
            if vtype == "enum" and (
                not isinstance(options, list)
                or not [o for o in options if str(o).strip()]
            ):
                raise ValueError(f"enum 变量 {key!r} 缺少 options")
            entry: Dict[str, Any] = {
                "key": key,
                "label": str(item.get("label") or key),
                "type": vtype,
                "required": bool(item.get("required")),
            }
            if vtype == "enum":
                entry["options"] = [str(o) for o in options if str(o).strip()]
            if item.get("default") is not None:
                entry["default"] = item["default"]
            cleaned.append(entry)
        return cleaned

    def _clean_files(self, raw: Any) -> List[Dict[str, Any]]:
        if raw in (None, []):
            return []
        if not isinstance(raw, list):
            raise ValueError("files 必须为数组")
        cleaned: List[Dict[str, Any]] = []
        seen: Set[str] = set()
        for item in raw:
            if not isinstance(item, dict):
                raise ValueError("files 元素必须为对象")
            path = validate_manifest_path(str(item.get("path") or ""))
            if path in seen:
                raise ValueError(f"files.path 重复: {path!r}")
            seen.add(path)
            content = item.get("content_template")
            if content is None:
                raise ValueError(f"files {path!r} 缺少 content_template")
            render = item.get("render", True)
            if not isinstance(render, bool):
                raise ValueError(f"files {path!r} 的 render 必须为布尔")
            cleaned.append(
                {
                    "path": path,
                    "content_template": str(content),
                    "render": render,
                }
            )
        return cleaned

    def _validate_template_declaration(self, tpl: Dict[str, Any]) -> None:
        """声明形状校验（A15 声明期 / A2 使用期双重，G-33/三.4）。"""
        if not self.templates.is_valid_template_id(str(tpl.get("id") or "")):
            raise ValueError(f"模板 id 非法: {tpl.get('id')!r}")
        if not str(tpl.get("name") or "").strip():
            raise ValueError("模板 name 为空")
        self._clean_metadata_template(tpl.get("metadata_template") or {})
        self._clean_variables(tpl.get("variables") or [])
        self._clean_files(tpl.get("files") or [])

    # ================= 项目 CRUD（A1~A5） =================

    def list_projects(
        self,
        page: Any = None,
        page_size: Any = None,
        status: Any = None,
        search: Any = None,
    ) -> Dict[str, Any]:
        status_str = str(status or "").strip()
        if status_str and status_str not in PROJECT_STATUSES:
            raise ProjectError("PRJ_101", f"status 非法: {status_str}")
        page_num = clamp_page(page)
        size = clamp_page_size(
            page_size,
            default=PROJECT_LIST_PAGE_SIZE_DEFAULT,
            max_size=100,
        )
        search_str = str(search or "").strip().lower()
        all_projects = self.store.list_projects()
        matched: List[Dict[str, Any]] = []
        for project in all_projects:
            if status_str and str(project.get("status") or "active") != status_str:
                continue
            if search_str:
                haystack = (
                    str(project.get("name") or "")
                    + "\n"
                    + str(project.get("description") or "")
                ).lower()
                if search_str not in haystack:
                    continue
            matched.append(project)
        total = len(matched)
        start = (page_num - 1) * size
        items = [self._summary(p) for p in matched[start : start + size]]
        return {"items": items, "total": total, "page": page_num, "page_size": size}

    def _summary(self, project: Dict[str, Any]) -> Dict[str, Any]:
        metadata = project.get("metadata") or {}
        collections = project.get("collections") or []
        last = (project.get("statistics") or {}).get("last_execution") or {}
        return {
            "id": project.get("id"),
            "name": project.get("name", ""),
            "description": project.get("description", ""),
            "status": project.get("status", "active"),
            "collection_count": len(collections),
            "request_count": sum(
                int(c.get("request_count") or 0) for c in collections
            ),
            "owner": metadata.get("owner", ""),
            "tags": metadata.get("tags", []),
            "created_at": metadata.get("created_at", ""),
            "updated_at": metadata.get("updated_at", ""),
            "last_execution": {
                "time": last.get("time", ""),
                "status": last.get("status", ""),
            }
            if last
            else None,
        }

    def get_project(self, project_id: str) -> Dict[str, Any]:
        """A3：读取 + 懒对账（G-30 三分支），变更时锁内回写。"""
        self._require_id(project_id)
        with self.store.exclusive():
            project = self.store.get_project(project_id)
            if project is None:
                raise ProjectError("PRJ_102", f"项目不存在: {project_id}", 404)
            if self.reconcile_executions(project):
                self.store.save_project(project)
        return project

    def create_project(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """A2：模板驱动创建；project.json 最后写=提交标记；异常全量回滚（G-17）。"""
        if not isinstance(payload, dict):
            raise ProjectError("PRJ_201", "请求体必须为 JSON 对象")
        name = str(payload.get("name") or "").strip()
        if not name:
            raise ProjectError("PRJ_201", "项目名称不能为空")
        template_id = str(payload.get("template_id") or "").strip()
        template = self.load_template_merged(template_id)

        answers = self._validate_answers(template, payload.get("variables"))
        self._ensure_name_unique(name)
        environment = self._validate_environment(
            (payload.get("config") or {}).get("environment")
        )

        project_id = self._prepare_dir_with_retry()
        try:
            project = self._build_project(
                payload, template, answers, name, project_id, environment
            )
            self.store.save_project(project)
        except ProjectError:
            self.store.rollback_project_dir(project_id)
            raise
        except Exception as exc:
            self.store.rollback_project_dir(project_id)
            logger.error("项目创建失败已回滚 %s: %s", project_id, exc)
            raise ProjectError("PRJ_205", f"创建失败已回滚: {exc}", 500)
        logger.info("已创建项目: %s (%s)", project_id, name)
        return project

    def _prepare_dir_with_retry(self) -> str:
        """G-18：uuid id 冲突（FileExistsError）重试一次。"""
        for _ in range(2):
            project_id = self.store.generate_project_id()
            try:
                self.store.prepare_new_project_dir(project_id)
                return project_id
            except FileExistsError:
                continue
        raise ProjectError("PRJ_205", "项目 id 生成冲突，请重试", 500)

    def _ensure_name_unique(self, name: str) -> None:
        for project in self.store.list_projects():
            if str(project.get("name") or "").strip() == name:
                raise ProjectError("PRJ_204", f"项目名称已存在: {name}", 409)

    def _validate_environment(self, raw: Any) -> str:
        env = str(raw or "").strip()
        if env and env not in ENVIRONMENTS:
            raise ProjectError("PRJ_501", f"环境不存在: {env}")
        return env

    def _validate_answers(
        self, template: Dict[str, Any], raw: Any
    ) -> Dict[str, Any]:
        answers = raw if isinstance(raw, dict) else {}
        for var in template.get("variables") or []:
            key = str(var.get("key") or "")
            vtype = str(var.get("type") or "string")
            value = answers.get(key)
            empty = value is None or (
                isinstance(value, str) and not value.strip()
            )
            if var.get("required") and empty:
                raise ProjectError("PRJ_202", f"缺少必填变量: {var.get('label', key)}")
            if empty:
                default = var.get("default")
                if vtype == "bool":
                    answers[key] = bool(default) if default is not None else False
                else:
                    answers[key] = ""
                continue
            if vtype == "enum":
                options = [str(o) for o in var.get("options") or []]
                if str(value) not in options:
                    raise ProjectError(
                        "PRJ_202", f"变量 {key} 取值越界: {value!r}，允许 {options}"
                    )
        return answers

    def _masked_answers(
        self, template: Dict[str, Any], answers: Dict[str, Any]
    ) -> Dict[str, Any]:
        secret_keys = {
            str(v.get("key"))
            for v in (template.get("variables") or [])
            if str(v.get("type") or "") == "secret"
        }
        return {
            k: ("***" if k in secret_keys else v) for k, v in answers.items()
        }

    def _build_project(
        self,
        payload: Dict[str, Any],
        template: Dict[str, Any],
        answers: Dict[str, Any],
        name: str,
        project_id: str,
        environment: str,
    ) -> Dict[str, Any]:
        now = _now_iso()
        unresolved: Set[str] = set()
        context: Dict[str, Any] = dict(answers)
        context.setdefault("project_name", name)
        context.setdefault("description", str(payload.get("description") or ""))

        metadata_template = template.get("metadata_template") or {}
        metadata: Dict[str, Any] = {}
        for key, value in metadata_template.items():
            metadata[str(key)] = self._render_text(
                str(value), context, unresolved
            )
        extra_meta = payload.get("metadata")
        if isinstance(extra_meta, dict):
            for key in ("jira_ids", "tags"):
                raw_list = extra_meta.get(key)
                if isinstance(raw_list, list):
                    metadata[key] = [str(x) for x in raw_list]
            for key in ("system", "module", "owner"):
                if str(extra_meta.get(key) or "").strip():
                    metadata[key] = str(extra_meta[key]).strip()
        metadata.setdefault("jira_ids", [])
        metadata.setdefault("tags", [])
        metadata["created_at"] = now
        metadata["updated_at"] = now
        metadata["version"] = str(template.get("version") or "1.0.0")

        written = self.render_template_files(
            project_id, template, context, unresolved=unresolved
        )
        metadata["_unresolved"] = sorted(unresolved)
        collections, docs = self._index_generated_files(project_id, written)
        tracing_meta = {
            "enabled": True,
            "file": "tracing.json",
            "updated_at": now,
        }
        if "tracing.json" not in written:
            self.store.write_project_json(
                project_id, "tracing.json", {"schema_version": SCHEMA_VERSION, "rows": []}
            )

        raw_cfg = payload.get("config")
        config_payload: Dict[str, Any] = raw_cfg if isinstance(raw_cfg, dict) else {}
        raw_exec = config_payload.get("execution")
        execution: Dict[str, Any] = raw_exec if isinstance(raw_exec, dict) else {}
        base_project: Dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "id": project_id,
            "name": name,
            "description": str(payload.get("description") or "").strip(),
            "status": str(payload.get("status") or "active").strip(),
            "metadata": metadata,
            "config": {
                "environment": environment,
                "base_url": str(config_payload.get("base_url") or "").strip(),
                "execution": {
                    "timeout_ms": int(execution.get("timeout_ms", 30000) or 30000),
                    "retry_count": int(execution.get("retry_count", 2) or 0),
                    "concurrent": bool(execution.get("concurrent", False)),
                },
                "notification": {"enabled": False},
                "auth_profile": "",
            },
            "collections": collections,
            "tracing": tracing_meta,
            "statistics": {"last_execution": None, "execution_history": []},
            "docs": docs,
            "template_info": {
                "id": template.get("id"),
                "version": template.get("version", "1.0.0"),
                "source": template.get("source", "builtin"),
                "answers": self._masked_answers(template, answers),
            },
        }
        base_project["status"] = (
            base_project["status"]
            if base_project["status"] in PROJECT_STATUSES
            else "active"
        )
        return base_project

    def render_template_files(
        self,
        project_id: str,
        template: Dict[str, Any],
        context: Dict[str, Any],
        unresolved: Optional[Set[str]] = None,
    ) -> Set[str]:
        """files manifest 通用生成引擎（G-32）：路径守卫→受限替换→原子写。

        collections/ 前缀的项统一落服务端 col_id 文件名（G-19）。
        返回实际落盘的相对路径集合（tracing.json 以原名计入）。
        unresolved 传入时收集未解析占位符键（G-20，与 metadata._unresolved 同源）。
        """
        written: Set[str] = set()
        missing: Set[str] = unresolved if unresolved is not None else set()
        for item in template.get("files") or []:
            path = validate_manifest_path(str(item.get("path") or ""))
            content_tpl = str(item.get("content_template") or "")
            render = bool(item.get("render", True))
            text = (
                self._render_text(content_tpl, context, missing)
                if render
                else content_tpl
            )
            target = path
            if path.startswith("collections/"):
                col_id = f"col_{uuid.uuid4().hex[:12]}"
                target = f"collections/{col_id}.json"
            if target.endswith(".json"):
                try:
                    data = json.loads(text)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"生成物 {target} 不是合法 JSON: {exc}")
                self.store.write_project_json(project_id, target, data)
            else:
                self.store.write_project_text(project_id, target, text)
            written.add(target)
        return written

    def _render_text(
        self, text: str, context: Dict[str, Any], unresolved: Set[str]
    ) -> str:
        def sub(match: "re.Match[str]") -> str:
            key = match.group(1)
            value = _norm_value_for_render(context.get(key))
            if value is None:
                unresolved.add(key)
                return ""
            return value

        return _PLACEHOLDER_RE.sub(sub, text)

    def _index_generated_files(
        self, project_id: str, written: Set[str]
    ) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
        now = _now_iso()
        collections: List[Dict[str, Any]] = []
        for rel in sorted(written):
            if not rel.startswith("collections/"):
                continue
            col_id = Path(rel).stem
            data = self.store.read_project_json(project_id, rel)
            info = data.get("info") if isinstance(data, dict) else None
            name = ""
            request_count = 0
            if isinstance(data, dict):
                request_count = _count_requests(data.get("item"))
                if isinstance(info, dict):
                    name = str(info.get("name") or "")
            collections.append(
                {
                    "id": col_id,
                    "name": name or col_id,
                    "file": rel,
                    "request_count": request_count,
                    "created_at": now,
                }
            )
        docs: Dict[str, str] = {}
        if "docs/README.md" in written:
            docs["readme"] = "docs/README.md"
        if "docs/troubleshooting.md" in written:
            docs["troubleshooting"] = "docs/troubleshooting.md"
        return collections, docs

    def update_project(
        self, project_id: str, updates: Dict[str, Any]
    ) -> Dict[str, Any]:
        """A4：白名单 name/description/status/metadata/config + updated_at CAS（G-36）。

        CAS 冲突 → 409 PRJ_306，data 携带最新对象供前端合并。
        """
        self._require_id(project_id)
        if not isinstance(updates, dict):
            raise ProjectError("PRJ_303", "请求体必须为 JSON 对象")
        expected_updated_at = str(updates.get("updated_at") or "").strip()
        if not expected_updated_at:
            raise ProjectError("PRJ_303", "缺少 updated_at（乐观锁 CAS 必填）")
        with self.store.exclusive():
            project = self.store.get_project(project_id)
            if project is None:
                raise ProjectError("PRJ_102", f"项目不存在: {project_id}", 404)
            current_updated_at = str(
                (project.get("metadata") or {}).get("updated_at") or ""
            )
            if current_updated_at != expected_updated_at:
                raise ProjectError(
                    "PRJ_306", "项目已被他人修改，请刷新后重试", 409, data=project
                )

            if "name" in updates:
                name = str(updates.get("name") or "").strip()
                if not name:
                    raise ProjectError("PRJ_303", "项目名称不能为空")
                if name != project.get("name"):
                    self._ensure_name_unique(name)
                    project["name"] = name
            if "description" in updates:
                project["description"] = str(updates.get("description") or "")
            if "status" in updates:
                status = str(updates.get("status") or "").strip()
                if status not in PROJECT_STATUSES:
                    raise ProjectError(
                        "PRJ_304",
                        f"status 非法: {status}，允许 {list(PROJECT_STATUSES)}",
                    )
                project["status"] = status
            if "metadata" in updates:
                raw_meta = updates.get("metadata")
                if not isinstance(raw_meta, dict):
                    raise ProjectError("PRJ_303", "metadata 必须为对象")
                metadata = project.get("metadata") or {}
                for key, value in raw_meta.items():
                    if key in ("_unresolved", "created_at", "updated_at", "version"):
                        continue
                    metadata[str(key)] = value
                project["metadata"] = metadata
            if "config" in updates:
                raw_cfg = updates.get("config")
                if not isinstance(raw_cfg, dict):
                    raise ProjectError("PRJ_303", "config 必须为对象")
                config = project.get("config") or {}
                if "environment" in raw_cfg:
                    config["environment"] = self._validate_environment(
                        raw_cfg.get("environment")
                    )
                for key in ("base_url", "execution", "notification"):
                    if key in raw_cfg:
                        config[key] = raw_cfg[key]
                project["config"] = config

            project.setdefault("metadata", {})["updated_at"] = _now_iso()
            self.store.save_project(project)
            return project

    def delete_project(self, project_id: str, confirmed: Any = False) -> Dict[str, Any]:
        """A5：需显式确认（后端删除防护），否则 403 PRJ_305。"""
        self._require_id(project_id)
        if confirmed is not True and str(confirmed).lower() not in ("1", "true", "yes"):
            raise ProjectError(
                "PRJ_305", "删除需二次确认：请求体携带 confirm=true", 403
            )
        if not self.store.delete_project(project_id):
            raise ProjectError("PRJ_102", f"项目不存在: {project_id}", 404)
        return {"deleted": project_id}

    def _require_id(self, project_id: str) -> None:
        if not self.store.is_valid_project_id(project_id):
            raise ProjectError("PRJ_301", f"项目 id 非法: {project_id!r}")

    # ================= 集合（A6~A8） =================

    def list_collections(self, project_id: str) -> Dict[str, Any]:
        project = self._load_project(project_id)
        return {"items": project.get("collections") or []}

    def add_collection(
        self, project_id: str, collection: Any, name: Any = None
    ) -> Dict[str, Any]:
        """A7：编辑器保存或上传解析后的 Collection 对象入库（≤50）。"""
        with self.store.exclusive():
            project = self._load_project(project_id)
            collections = project.get("collections") or []
            if len(collections) >= PROJECT_MAX_COLLECTIONS:
                raise ProjectError(
                    "PRJ_403",
                    f"Collection 数量已达上限 {PROJECT_MAX_COLLECTIONS}",
                    409,
                )
            if not isinstance(collection, dict) or not (
                isinstance(collection.get("info"), dict)
                or isinstance(collection.get("item"), list)
            ):
                raise ProjectError(
                    "PRJ_401", "Collection 结构非法：需为含 info/item 的 Postman 导出对象"
                )
            col_id = f"col_{uuid.uuid4().hex[:12]}"
            rel = f"collections/{col_id}.json"
            info = collection.get("info")
            col_name = str(name or "").strip() or (
                str(info.get("name")) if isinstance(info, dict) and info.get("name") else col_id
            )
            try:
                self.store.write_project_json(project_id, rel, collection)
            except OSError as exc:
                raise ProjectError("PRJ_402", f"Collection 写入失败: {exc}", 500)
            entry = {
                "id": col_id,
                "name": col_name,
                "file": rel,
                "request_count": _count_requests(collection.get("item")),
                "created_at": _now_iso(),
            }
            collections.append(entry)
            project["collections"] = collections
            self._touch(project)
            self.store.save_project(project)
            return entry

    def remove_collection(
        self, project_id: str, col_id: str
    ) -> Dict[str, Any]:
        """A8：移除集合（tracing 行不做级联删除，仅 GET 派生 dangling 提示）。"""
        with self.store.exclusive():
            project = self._load_project(project_id)
            collections = project.get("collections") or []
            target = next(
                (c for c in collections if str(c.get("id")) == str(col_id)), None
            )
            if target is None:
                raise ProjectError("PRJ_404", f"Collection 不存在: {col_id}", 404)
            collections.remove(target)
            project["collections"] = collections
            rel = str(target.get("file") or "")
            if rel:
                try:
                    self.store.delete_project_file(project_id, rel)
                except ValueError:
                    logger.warning("集合文件路径非法，保留文件: %s", rel)
            self._touch(project)
            self.store.save_project(project)
            return {"items": collections}

    # ================= 追溯（A10/A11） =================

    def get_tracing(self, project_id: str) -> Dict[str, Any]:
        project = self._load_project(project_id)
        rel = str((project.get("tracing") or {}).get("file") or "tracing.json")
        data = self.store.read_project_json(project_id, rel)
        if data is None:
            raise ProjectError("PRJ_601", "追溯表不存在", 404)
        rows = data.get("rows") if isinstance(data, dict) else None
        if not isinstance(rows, list):
            rows = []
        known_col_ids = {
            str(c.get("id")) for c in (project.get("collections") or [])
        }
        derived_rows: List[Any] = []
        for row in rows:
            if isinstance(row, dict):
                item = dict(row)
                cid = str(item.get("collection_id") or "")
                item["dangling"] = bool(cid) and cid not in known_col_ids
                derived_rows.append(item)
            else:
                derived_rows.append(row)
        stats = self._tracing_stats(derived_rows, project)
        return {
            "rows": derived_rows,
            **stats,
            "updated_at": str((project.get("tracing") or {}).get("updated_at") or ""),
        }

    def _tracing_stats(
        self, rows: List[Any], project: Dict[str, Any]
    ) -> Dict[str, Any]:
        total = len(rows)
        automated = sum(
            1
            for r in rows
            if isinstance(r, dict)
            and str(r.get("convert_status")) == "automated"
        )
        rate = round(automated * 100.0 / total, 2) if total else 0.0
        return {"total": total, "automated": automated, "rate": rate}

    def put_tracing(
        self, project_id: str, rows: Any, updated_at: Any
    ) -> Dict[str, Any]:
        """A11：整表替换 + updated_at 乐观锁（G-36）；行格式非法 PRJ_603。"""
        normalized = self._normalize_tracing_rows(rows)
        expected = str(updated_at or "").strip()
        if not expected:
            raise ProjectError("PRJ_602", "缺少 updated_at（追溯表 CAS 必填）", 409)
        with self.store.exclusive():
            project = self._load_project(project_id)
            tracing = project.get("tracing") or {}
            if str(tracing.get("updated_at") or "") != expected:
                data = self.get_tracing(project_id)
                raise ProjectError(
                    "PRJ_602", "追溯表已被他人修改，请刷新后重试", 409, data=data
                )
            rel = str(tracing.get("file") or "tracing.json")
            self.store.write_project_json(
                project_id,
                rel,
                {"schema_version": SCHEMA_VERSION, "rows": normalized},
            )
            now = _now_iso()
            project.setdefault("tracing", {})["updated_at"] = now
            self.store.save_project(project)
            stats = self._tracing_stats(normalized, project)
            return {**stats, "updated_at": now}

    def _normalize_tracing_rows(self, rows: Any) -> List[Dict[str, Any]]:
        if not isinstance(rows, list):
            raise ProjectError("PRJ_603", "追溯表必须为行数组")
        normalized: List[Dict[str, Any]] = []
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                raise ProjectError("PRJ_603", f"第 {index + 1} 行必须为对象")
            case_no = str(row.get("case_no") or "").strip()
            title = str(row.get("title") or "").strip()
            if not case_no or not title:
                raise ProjectError("PRJ_603", f"第 {index + 1} 行缺少 case_no/title")
            convert_status = str(row.get("convert_status") or "pending").strip()
            if convert_status not in TRACING_CONVERT_STATUSES:
                raise ProjectError(
                    "PRJ_603",
                    f"第 {index + 1} 行 convert_status 非法: {convert_status}",
                )
            entry: Dict[str, Any] = {
                "case_no": case_no,
                "title": title,
                "priority": str(row.get("priority") or "").strip(),
                "convert_status": convert_status,
                "collection_id": str(row.get("collection_id") or "").strip(),
                "request_id": str(row.get("request_id") or "").strip(),
            }
            normalized.append(entry)
        return normalized

    # ================= 执行入队（A9，S3.1） =================

    def execute_project(self, project_id: str) -> Dict[str, Any]:
        """A9：合并集合→临时文件→与手工执行同队列入队（v2 R3）→入队即记录（G-30）。"""
        project = self._load_project(project_id)
        collections = project.get("collections") or []
        if not collections:
            raise ProjectError("PRJ_502", "无集合可执行", 409)

        merged_items: List[Any] = []
        for entry in collections:
            rel = str(entry.get("file") or "")
            if not rel:
                continue
            try:
                data = self.store.read_project_json(project_id, rel)
            except (OSError, ValueError):
                logger.warning("读取集合文件失败，跳过: %s/%s", project_id, rel)
                continue
            if isinstance(data, dict) and isinstance(data.get("item"), list):
                merged_items.extend(data["item"])
        if not merged_items:
            raise ProjectError("PRJ_502", "无集合可执行", 409)

        config = project.get("config") or {}
        env_name = str(config.get("environment") or "").strip()
        if env_name and env_name not in ENVIRONMENTS:
            raise ProjectError("PRJ_501", f"环境不存在: {env_name}")
        base_url = str(config.get("base_url") or "").strip() or None
        token: Optional[str] = None
        env_cfg = ENVIRONMENTS.get(env_name) if env_name else None
        if isinstance(env_cfg, dict):
            # env fallback 镜像 job_routes.api_run_postman：表单空值回退环境配置
            if not base_url and str(env_cfg.get("base_url") or "").strip():
                env_base = str(env_cfg["base_url"]).strip()
                if is_valid_http_url(env_base):
                    base_url = env_base
            token = str(env_cfg.get("token") or "").strip() or None
        if base_url and not is_valid_http_url(base_url):
            raise ProjectError("PRJ_501", f"base_url 非法: {base_url}")

        collection_data = {
            "info": {
                "name": str(project.get("name") or project_id),
                "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
            },
            "item": merged_items,
        }
        job_id = uuid.uuid4().hex
        saved_file = build_saved_json_path(UPLOADS_DIR, job_id)
        try:
            save_collection_json(saved_file, collection_data)
        except OSError as exc:
            raise ProjectError("PRJ_503", f"入队失败: {exc}", 500) from exc

        # 延迟 import：避免服务层在启动期拖入 app 工厂重依赖
        from postman_api_tester.report_server_app import ReportServerApp

        reports_dir = ReportServerApp._resolve_reports_dir()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        # 含 .html 且嵌 job_id → 执行器原样落盘不撞名 → find_report 逐字节命中（G-30 对账）
        report_name = f"project_{project_id}_{ts}_{job_id[:8]}.html"
        job_params = build_run_postman_job_params(
            job_id=job_id,
            original_name=f"{project.get('name') or project_id}.json",
            saved_file=str(saved_file),
            output_dir=str(reports_dir),
            report_name=report_name,
            base_url=base_url,
            token=token,
            selected_item_paths=None,
            env_name=env_name,
        )
        try:
            enqueue_job_with_worker(
                job_id,
                str(saved_file),
                job_params,
                RUN_RESULTS_PER_PAGE_DEFAULT,
                run_postman_job_fn=_RUN_POSTMAN_JOB_FN,
                set_run_job=set_run_job,
                default_output_dir=str(reports_dir),
            )
        except Exception as exc:
            logger.error("项目执行入队失败 %s: %s", project_id, exc)
            raise ProjectError("PRJ_503", f"入队失败: {exc}", 500) from exc

        self.record_execution_enqueued(project_id, job_id, report_name)
        return {"job_id": job_id, "report_name": report_name, "status": "queued"}

    # ================= 执行历史（G-30 状态机） =================

    def record_execution_enqueued(
        self, project_id: str, job_id: str, report_name: str
    ) -> Dict[str, Any]:
        """A9 入队成功后同步写 history 头条（入队即记录）。"""
        entry = {
            "job_id": job_id,
            "report_name": report_name,
            "time": _now_iso(),
            "status": "queued",
            "passed": None,
            "failed": None,
        }

        def mutator(project: Dict[str, Any]) -> Dict[str, Any]:
            stats = project.setdefault("statistics", {})
            history: List[Dict[str, Any]] = stats.setdefault(
                "execution_history", []
            )
            history.insert(0, entry)
            del history[PROJECT_EXECUTION_HISTORY_MAX:]
            stats["last_execution"] = dict(entry)
            self._touch(project)
            return project

        updated = self.store.update_project(project_id, mutator)
        if updated is None:
            raise ProjectError("PRJ_102", f"项目不存在: {project_id}", 404)
        return entry

    def reconcile_executions(self, project: Dict[str, Any]) -> bool:
        """对 pending 历史条目懒对账（G-30 三分支：内存→报告→unknown）。

        真值优先级：报告（磁盘）> 任务内存 > unknown。返回是否有变更。
        调用方需持锁（get_project 已包 exclusive）。
        """
        stats = project.get("statistics") or {}
        history = stats.get("execution_history") or []
        changed = False
        for entry in history:
            if not isinstance(entry, dict):
                continue
            if str(entry.get("status") or "") not in PENDING_HISTORY_STATUSES:
                continue
            job_id = str(entry.get("job_id") or "")
            job = get_run_job(job_id) if job_id else None
            if job is not None:
                job_status = str(job.get("status") or "")
                if job_status in ("queued", "running"):
                    if job_status == "running" and entry.get("status") != "running":
                        entry["status"] = "running"
                        changed = True
                    continue
                # success/failed/error：内存终态；计数以报告为准（报告可能尚未刷出）
                new_status = "done" if job_status == "success" else "failed"
                if entry.get("status") != new_status:
                    entry["status"] = new_status
                    changed = True
                if entry.get("passed") is None:
                    counts = self._report_counts(
                        str(entry.get("report_name") or "")
                    )
                    if counts is not None:
                        entry["passed"], entry["failed"] = counts
                        changed = True
            else:
                # 内存 miss（重启/淘汰）→ 报告存在则 done，否则 unknown 终态
                counts = self._report_counts(str(entry.get("report_name") or ""))
                if counts is not None:
                    entry["status"] = "done"
                    entry["passed"], entry["failed"] = counts
                else:
                    entry["status"] = "unknown"
                changed = True
        if history and stats.get("last_execution") != history[0]:
            stats["last_execution"] = history[0]
            changed = True
        return changed

    def _report_counts(self, report_name: str) -> Optional[Tuple[int, int]]:
        if not report_name:
            return None
        try:
            report = find_report(report_name)
        except FileNotFoundError:
            return None
        except Exception as exc:
            logger.warning("对账读取报告失败 %s: %s", report_name, exc)
            return None
        try:
            return (
                int(str(report.get("passed") or 0)),
                int(str(report.get("failed") or 0)),
            )
        except (TypeError, ValueError):
            return None

    # ================= 公共小工具 =================

    def _load_project(self, project_id: str) -> Dict[str, Any]:
        self._require_id(project_id)
        project = self.store.get_project(project_id)
        if project is None:
            raise ProjectError("PRJ_102", f"项目不存在: {project_id}", 404)
        return project

    def _touch(self, project: Dict[str, Any]) -> None:
        project.setdefault("metadata", {})["updated_at"] = _now_iso()


_default_service: Optional[ProjectService] = None


def get_project_service() -> ProjectService:
    global _default_service
    if _default_service is None:
        _default_service = ProjectService()
    return _default_service
