"""项目脚手架 HTTP 处理层（v1.39.0，功能默认关闭）。

开发导读:
- 3 页面壳（模板 N7~N9 在阶段 2 交付）+ 15 API，共 18 个处理函数；
  本文件只导出函数，路由唯一装配点在 report_server.py（v2 冲突 2）。
- 统一契约：
  * 开关关（G-25）：API 返回 403 PRJ_100 JSON 包装体；页面返回 403 提示页。
  * project_api 装饰器：门控 → ProjectError（动态码/状态；CAS 冲突时
    data.current 携带最新对象供前端合并）→ ValueError 兜底（PRJ_301，
    对应 store 的 id/路径守卫）→ 未预期异常兜底（PRJ_999，500）。
  * POST/PUT 一律 `request.get_json(silent=True) or {}`（G-34：
    非法 JSON 不外漏 Flask 默认 HTML 400 页）。
  * 成功统一 `BaseHandler.json_response`（code 为 HTTP 数字，L-1）；
    错误体顶层 `error_code` 承载 PRJ_/TPL_ 业务码（v2 冲突 1）。
- 端点参数一律默认 string 转换器，禁 `<path:...>`（G-38）；路径表见 v3 5.2。
"""

import logging
from datetime import datetime
from functools import wraps
from typing import Any, Callable, Dict, Tuple, Type

from flask import jsonify, make_response, render_template, request
from flask.typing import ResponseReturnValue

from postman_api_tester.config import ENABLE_PROJECT_SCAFFOLD
from postman_api_tester.handlers.base_handler import (
    BaseHandler,
    handle_api_errors,
    json_error,
)
from postman_api_tester.services.project_service import (
    ProjectError,
    get_project_service,
)

logger = logging.getLogger(__name__)

# 非 ProjectError 逃逸的统一兜底映射（ProjectError 由 project_api 先捕获）：
# ValueError 主要来自 store 的 id/路径守卫 → 400 PRJ_301（id 非法）。
PROJECT_ERROR_MAP: Dict[Type[Exception], Tuple[int, str]] = {
    ValueError: (400, "PRJ_301")
}

# 开关关闭时的页面提示（不进 API 包装体，页面返回 HTML 语义）
_DISABLED_PAGE_HTML = (
    "<h1>403 Forbidden</h1>"
    "<p>项目脚手架功能未启用：请设置环境变量 ENABLE_PROJECT_SCAFFOLD=true 后重启服务。</p>"
)


def _project_error_response(exc: ProjectError) -> ResponseReturnValue:
    """ProjectError → L-1 统一错误体（镜像 BaseHandler.error_response 结构）。

    与 json_error 的差异仅在业务可控：error_code=exc.code、code=exc.http_status，
    且 exc.data 非空时挂到 data.current（A4/A11 CAS 冲突合并用）。
    """
    data: Dict[str, Any] = {"error": "ProjectError", "details": exc.message}
    if exc.data is not None:
        data["current"] = exc.data
    body: Dict[str, Any] = {
        "code": exc.http_status,
        "message": "Error",
        "data": data,
        "timestamp": datetime.now().isoformat(),
        "error_code": exc.code,
    }
    return jsonify(body), exc.http_status


def project_api(func: Callable[..., ResponseReturnValue]) -> Callable[..., ResponseReturnValue]:
    """脚手架 API 统一装饰器：开关门控 + 业务/兜底异常映射。

    捕获顺序：开关关→403 PRJ_100；ProjectError→动态码；ValueError→400 PRJ_301
    （经 handle_api_errors）；其余→500 PRJ_999。
    """
    guarded = handle_api_errors(PROJECT_ERROR_MAP)(func)

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> ResponseReturnValue:
        if not ENABLE_PROJECT_SCAFFOLD:
            return json_error(
                "项目脚手架功能未启用，请设置 ENABLE_PROJECT_SCAFFOLD=true",
                403,
                "PRJ_100",
            )
        try:
            return guarded(*args, **kwargs)
        except ProjectError as exc:
            return _project_error_response(exc)
        except Exception as exc:
            logger.exception("%s 未预期异常", func.__name__)
            return json_error(str(exc), 500, "PRJ_999")

    return wrapper


def _json_body() -> Any:
    """G-34：非法 JSON 静默为 {}，由 service 层按端点语义报 400。"""
    return request.get_json(silent=True) or {}


# ==================== P1~P3 页面壳 ====================


def projects_page() -> ResponseReturnValue:
    """P1 GET /projects 列表壳页（模板 N7，阶段 2 交付）。"""
    if not ENABLE_PROJECT_SCAFFOLD:
        return make_response(_DISABLED_PAGE_HTML, 403)
    return render_template("project_index.html")


def projects_create_page() -> ResponseReturnValue:
    """P2 GET /projects/create 创建壳页（模板 N8）。"""
    if not ENABLE_PROJECT_SCAFFOLD:
        return make_response(_DISABLED_PAGE_HTML, 403)
    return render_template("project_create.html")


def projects_detail_page(project_id: str) -> ResponseReturnValue:
    """P3 GET /projects/detail/<project_id> 详情壳页（模板 N9，含内嵌编辑）。

    存在性/权限判断一律放 API 层（壳页 + 客户端 fetch 模式，v2 冲突 7）。
    """
    if not ENABLE_PROJECT_SCAFFOLD:
        return make_response(_DISABLED_PAGE_HTML, 403)
    return render_template("project_detail.html", project_id=project_id)


# ==================== A1~A5 项目 CRUD ====================


@project_api
def api_list_projects() -> ResponseReturnValue:
    """A1 GET /api/projects → {items, total, page, page_size}；错误码 PRJ_101。"""
    result = get_project_service().list_projects(
        page=request.args.get("page", type=int),
        page_size=request.args.get("page_size", type=int),
        status=request.args.get("status"),
        search=request.args.get("search"),
    )
    return BaseHandler.json_response(result)


@project_api
def api_create_project() -> ResponseReturnValue:
    """A2 POST /api/projects 按模板创建 → 完整 project；错误码 PRJ_201~205。"""
    return BaseHandler.json_response(get_project_service().create_project(_json_body()))


@project_api
def api_get_project(project_id: str) -> ResponseReturnValue:
    """A3 GET /api/projects/<project_id> → 完整 project（含懒对账后 history）；PRJ_301/102。"""
    return BaseHandler.json_response(get_project_service().get_project(project_id))


@project_api
def api_update_project(project_id: str) -> ResponseReturnValue:
    """A4 PUT /api/projects/<project_id> 白名单更新；PRJ_303/304/306。

    请求体必须回传 updated_at（CAS）；409 冲突体 data.current 携带最新对象。
    """
    return BaseHandler.json_response(
        get_project_service().update_project(project_id, _json_body())
    )


@project_api
def api_delete_project(project_id: str) -> ResponseReturnValue:
    """A5 DELETE /api/projects/<project_id> → {deleted}；未确认 403 PRJ_305。"""
    body = _json_body()
    confirmed = body.get("confirm", False) if isinstance(body, dict) else False
    result = get_project_service().delete_project(project_id, confirmed)
    return BaseHandler.json_response(result)


# ==================== A6~A8 项目集合 ====================


@project_api
def api_list_project_collections(project_id: str) -> ResponseReturnValue:
    """A6 GET /api/projects/<project_id>/collections → {items}；PRJ_102。"""
    return BaseHandler.json_response(
        get_project_service().list_collections(project_id)
    )


@project_api
def api_add_project_collection(project_id: str) -> ResponseReturnValue:
    """A7 POST /api/projects/<project_id>/collections → 新集合索引项。

    请求体 = Collection JSON 本体（info/item）；可选 ?name= 覆盖集合名。
    错误码 PRJ_401（结构非法）/402（写入失败）/403（超数量上限）。
    """
    entry = get_project_service().add_collection(
        project_id, _json_body(), name=request.args.get("name")
    )
    return BaseHandler.json_response(entry)


@project_api
def api_remove_project_collection(project_id: str, col_id: str) -> ResponseReturnValue:
    """A8 DELETE /api/projects/<id>/collections/<col_id> → 更新后索引；PRJ_404。"""
    result = get_project_service().remove_collection(project_id, col_id)
    return BaseHandler.json_response(result)


# ==================== A9 执行 ====================


@project_api
def api_execute_project(project_id: str) -> ResponseReturnValue:
    """A9 POST /api/projects/<project_id>/execute → {job_id, report_name, status}。

    真实入队见 project_service.execute_project（S3.1）：合并集合→临时文件→
    与手工执行同队列。错误码 PRJ_501（环境不存在/base_url 非法，400）、
    PRJ_502（无集合可执行，409）、PRJ_503（入队失败，500）。
    """
    result = get_project_service().execute_project(project_id)
    return BaseHandler.json_response(result)


# ==================== A10~A11 追溯表 ====================


@project_api
def api_get_project_tracing(project_id: str) -> ResponseReturnValue:
    """A10 GET /api/projects/<id>/tracing → {rows, total, automated, rate}；PRJ_601。"""
    return BaseHandler.json_response(get_project_service().get_tracing(project_id))


@project_api
def api_put_project_tracing(project_id: str) -> ResponseReturnValue:
    """A11 PUT /api/projects/<id>/tracing 整表替换 → 派生统计；PRJ_602/603。

    请求体 = {rows: [...], updated_at: "<GET 返回的 tracing.updated_at>"}。
    """
    body = _json_body()
    rows = body.get("rows") if isinstance(body, dict) else None
    updated_at = body.get("updated_at") if isinstance(body, dict) else None
    result = get_project_service().put_tracing(project_id, rows, updated_at)
    return BaseHandler.json_response(result)


# ==================== A12~A13 导出 ====================


@project_api
def api_export_project_tracing_csv(project_id: str) -> ResponseReturnValue:
    """A12 GET /api/projects/<id>/export/tracing.csv → text/csv 文件流；PRJ_601。"""
    csv_text, file_name = get_project_service().export_tracing_csv(project_id)
    resp = make_response(csv_text)
    resp.headers["Content-Type"] = "text/csv; charset=utf-8"
    resp.headers["Content-Disposition"] = f'attachment; filename="{file_name}"'
    return resp


@project_api
def api_export_project_zip(project_id: str) -> ResponseReturnValue:
    """A13 GET /api/projects/<id>/export → {file_name, url}（共享 EXPORTS_DIR）。

    G-37 命名 `proj_<id>_<UTC紧凑>_project.zip`，经 /exports/ 静态路由下载；
    错误码 PRJ_701（导出失败，500）。
    """
    result = get_project_service().export_project_zip(project_id)
    return BaseHandler.json_response(result)


# ==================== A14~A15 模板 ====================


@project_api
def api_list_project_templates() -> ResponseReturnValue:
    """A14 GET /api/project-templates → {items}（两源合并，含 source/variables）。"""
    return BaseHandler.json_response(get_project_service().list_templates())


@project_api
def api_create_project_template() -> ResponseReturnValue:
    """A15 POST /api/project-templates 创建用户模板 → 存储后的模板对象。

    请求体 = 完整 template.json（服务端重写 id/author/created_at，G-33）；
    错误码 TPL_001（非法）/TPL_002（撞内置只读）/TPL_003（写入失败）。
    """
    return BaseHandler.json_response(
        get_project_service().create_template(_json_body())
    )


@project_api
def api_delete_project_template(template_id: str) -> ResponseReturnValue:
    """A16 DELETE /api/project-templates/<template_id> → {deleted, id}。

    仅用户模板可删：内置 409 TPL_002；不存在 404 PRJ_203；非法 id 400 PRJ_301。
    """
    return BaseHandler.json_response(
        get_project_service().delete_template(template_id)
    )
