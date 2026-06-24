"""测试执行辅助函数。

职责：
- 运行时配置解析
- 检查点管理
- API 执行上下文准备
- 报告生成协调
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from datetime import datetime
from types import ModuleType
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING
if TYPE_CHECKING:
    from postman_api_tester.postman_api_tester import PostmanTestReport
from urllib.parse import urljoin

from postman_api_tester.core.batch_scheduler import BatchScheduler
from postman_api_tester.core.concurrent_executor import ConcurrentProgressTracker, execute_batch_concurrently
from postman_api_tester.core.html_reporter import HtmlReporter
from postman_api_tester.core.types import ProgressCallback, ProgressPayload
from postman_api_tester.exceptions import ValidationError
from postman_api_tester.parser import ApiConfig, PostmanApiParser
from postman_api_tester.auth import get_auth_token
from postman_api_tester.executor import PostmanTestExecutor, TestResultRecord
from postman_api_tester.session import (
    SessionLike,
    RequestTimeout,
    create_shared_session,
    close_session,
    normalize_timeout,
    resolve_request_timeout,
)
from postman_api_tester.runtime_utils import (
    checkpoint_file_path as _checkpoint_file_path,
    checkpoint_key as _checkpoint_key,
    compute_collection_fingerprint as _compute_collection_fingerprint,
    item_path_text as _item_path_text,
    load_checkpoint as _load_checkpoint,
    save_checkpoint_atomic as _save_checkpoint_atomic,
)
from postman_api_tester.utils.logging_utils import log_sampled, get_log_sample_rate

logger = logging.getLogger(__name__)
PASSED_TEST_LOG_SAMPLE_RATE = get_log_sample_rate(default=0.1)

def _resolve_runtime_config(
    token: Optional[str],
    base_url: Optional[str],
    output_dir: Optional[str],
) -> Tuple[Optional[str], Optional[str], Optional[str], bool, int, str, bool]:
    enable_checkpoint_recovery = False
    checkpoint_flush_every_n = 1
    checkpoint_dir = ""
    assertion_strict_mode = False

    try:
        from postman_api_tester import config as _cfg_module
        cfg: Optional[ModuleType] = _cfg_module

        cfg_token = str(getattr(cfg, 'TOKEN', '') or '').strip()
        if token is None and cfg_token:
            token = cfg_token

        cfg_base_url = str(getattr(cfg, 'BASE_URL', '') or '').strip()
        if base_url is None and cfg_base_url:
            base_url = cfg_base_url

        cfg_output_dir = str(getattr(cfg, 'REPORT_OUTPUT_DIR', '') or '').strip()
        if output_dir is None and cfg_output_dir:
            output_dir = cfg_output_dir

        enable_checkpoint_recovery = bool(getattr(cfg, 'ENABLE_CHECKPOINT_RECOVERY', False))
        checkpoint_flush_every_n = max(1, int(getattr(cfg, 'CHECKPOINT_FLUSH_EVERY_N', 1)))
        checkpoint_dir = str(getattr(cfg, 'CHECKPOINT_DIR', '') or '').strip()
        assertion_strict_mode = bool(getattr(cfg, 'ENABLE_ASSERTION_STRICT_MODE', False))
    except (ImportError, AttributeError, TypeError, ValueError):
        pass

    return (
        token,
        base_url,
        output_dir,
        enable_checkpoint_recovery,
        checkpoint_flush_every_n,
        checkpoint_dir,
        assertion_strict_mode,
    )


def _resolve_output_dir(output_dir: Optional[str]) -> str:
    if output_dir is not None:
        return output_dir
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'reports')


def _validate_base_url(base_url: Optional[str]) -> None:
    if base_url is None:
        return
    from urllib.parse import urlparse as _urlparse
    _parsed = _urlparse(base_url)
    if _parsed.scheme not in ("http", "https") or not _parsed.netloc:
        raise ValidationError(f"base_url 格式无效（仅支持 http/https）：{base_url!r}")


def _filter_selected_apis(
    apis: List[ApiConfig],
    selected_item_paths: Optional[List[List[int]]],
) -> Tuple[List[ApiConfig], Optional[set[tuple[int, ...]]]]:
    selected_path_set: Optional[set[tuple[int, ...]]] = None
    if selected_item_paths:
        normalized_paths = []
        for path in selected_item_paths:
            if not isinstance(path, list):
                continue
            if all(isinstance(index, int) and index >= 0 for index in path):
                normalized_paths.append(tuple(path))
        selected_path_set = set(normalized_paths)
        if not selected_path_set:
            raise ValidationError("selected_item_paths 格式无效，未解析到可执行接口路径。")

        apis = [
            api for api in apis
            if tuple(api.get('item_path') or []) in selected_path_set
        ]
        if not apis:
            raise ValidationError("未匹配到可执行接口，请确认所选接口是否仍存在于当前集合。")
    return apis, selected_path_set


def _prepare_checkpoint_recovery(
    *,
    enable_checkpoint_recovery: bool,
    output_dir: str,
    postman_file: str,
    parser_base_url: str,
    selected_item_paths: Optional[List[List[int]]],
    apis: List[ApiConfig],
    checkpoint_dir: str,
    data_file: str = "",
) -> Tuple[str, str, set[str], List[ApiConfig]]:
    checkpoint_path = ""
    collection_fingerprint = ""
    executed_item_paths: set[str] = set()

    if not enable_checkpoint_recovery:
        return checkpoint_path, collection_fingerprint, executed_item_paths, apis

    try:
        collection_fingerprint = _compute_collection_fingerprint(
            postman_file, parser_base_url, selected_item_paths, data_file=data_file,
        )
        checkpoint_path = _checkpoint_file_path(output_dir, postman_file, collection_fingerprint, checkpoint_dir=checkpoint_dir)
        checkpoint = _load_checkpoint(checkpoint_path)
        if checkpoint:
            fingerprint_match = str(checkpoint.get("collection_fingerprint") or "") == collection_fingerprint
            base_url_match = str(checkpoint.get("base_url") or "") == str(parser_base_url or "")
            if fingerprint_match and base_url_match:
                executed_item_paths = set(checkpoint.get("executed_item_paths") or [])
                if executed_item_paths:
                    original_count = len(apis)
                    apis = [
                        api for api in apis
                        if _checkpoint_key(
                            api.get("item_path"),
                            int(api.get("data_index", 0) or 0),
                        ) not in executed_item_paths
                    ]
                    logger.info("断点恢复生效，跳过已执行接口 %d 个，待执行 %d 个", original_count - len(apis), len(apis))
            else:
                logger.warning("检测到 checkpoint 与当前集合不匹配，已忽略恢复数据。")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        logger.warning("初始化 checkpoint 失败，已降级为普通执行: %s", exc)

    return checkpoint_path, collection_fingerprint, executed_item_paths, apis


def _parse_collection_apis(postman_file: str) -> Tuple[PostmanApiParser, List[ApiConfig], int]:
    logger.info("开始加载 Postman 文件: %s", postman_file)
    parser = PostmanApiParser(postman_file)
    apis = parser.extract_apis()
    total_apis_count = len(apis)
    return parser, apis, total_apis_count


def _log_execution_scope(
    *,
    current_count: int,
    total_apis_count: int,
    parser_base_url: str,
    selected_path_set: Optional[set[tuple[int, ...]]],
) -> None:
    logger.info("成功加载 %d 个 API 接口，基础 URL: %s", current_count, parser_base_url)
    if selected_path_set is not None:
        logger.info("本次执行范围：已选接口 %d / 全量 %d", current_count, total_apis_count)


def _resolve_checkpoint_execution_apis(
    *,
    enable_checkpoint_recovery: bool,
    output_dir: str,
    postman_file: str,
    parser_base_url: str,
    selected_item_paths: Optional[List[List[int]]],
    apis: List[ApiConfig],
    checkpoint_dir: str,
    data_file: str = "",
) -> Tuple[str, str, set[str], List[ApiConfig]]:
    apis_before_recovery = list(apis)
    checkpoint_path, collection_fingerprint, executed_item_paths, apis = _prepare_checkpoint_recovery(
        enable_checkpoint_recovery=enable_checkpoint_recovery,
        output_dir=output_dir,
        postman_file=postman_file,
        parser_base_url=parser_base_url,
        selected_item_paths=selected_item_paths,
        apis=apis,
        checkpoint_dir=checkpoint_dir,
        data_file=data_file,
    )
    if enable_checkpoint_recovery and not apis:
        # 防止生成空报告：若 checkpoint 覆盖全部接口，则回退为全量执行。
        logger.info("checkpoint 覆盖全部接口，本次回退为全量执行以保持报告可读性。")
        apis = apis_before_recovery
        executed_item_paths = set()
    return checkpoint_path, collection_fingerprint, executed_item_paths, apis


def _apply_base_url_override(
    parser: PostmanApiParser,
    apis: List[ApiConfig],
    base_url: Optional[str],
) -> None:
    if not base_url:
        return
    parser.base_url = base_url
    for api in apis:
        api['full_url'] = urljoin(base_url, api['url']) if not api['url'].startswith('http') else api['url']


def _emit_progress(progress_callback: Optional[ProgressCallback], payload: ProgressPayload) -> None:
    if not progress_callback:
        return
    try:
        progress_callback(payload)
    except Exception:
        # 外部回调异常不应中断执行流程，保持宽捕获。
        pass


def _emit_start_progress(
    progress_callback: Optional[ProgressCallback],
    *,
    current_total: int,
    total_apis_count: int,
) -> None:
    _emit_progress(progress_callback, {
        'stage': 'running',
        'total': current_total,
        'total_all': total_apis_count,
        'completed': 0,
        'percent': 0,
        'current_name': '',
        'current_method': '',
        'current_url': '',
        'message': '开始执行测试',
    })


def _resolve_auth_token(
    token: Optional[str],
    apis: List[ApiConfig],
    base_url: str,
    *,
    auth_session: SessionLike,
    request_timeout: RequestTimeout,
) -> Optional[str]:
    if token:
        logger.info("使用手动指定的 token: %s...", token[:20])
        return token

    auth_token = get_auth_token(apis, base_url, session=auth_session, request_timeout=request_timeout)

    if auth_token:
        logger.info("已获取认证 token: %s...", auth_token[:20])
    return auth_token


def _build_runtime_context(
    token: Optional[str],
    apis: List[ApiConfig],
    base_url: str,
) -> Tuple[Optional[str], RequestTimeout, SessionLike]:
    """Build runtime context with unified timeout and shared session lifecycle."""
    shared_session = create_shared_session()
    request_timeout = normalize_timeout(resolve_request_timeout(default=(10, 30)), default=(10, 30))
    resolved_token = _resolve_auth_token(
        token,
        apis,
        base_url,
        auth_session=shared_session,
        request_timeout=request_timeout,
    )
    return resolved_token, request_timeout, shared_session


def _resolve_report_file_path(output_dir: str, report_name: Optional[str]) -> str:
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    default_report_name = f'postman_report_{timestamp}.html'
    selected_report_name = str(report_name or '').strip()
    if selected_report_name:
        normalized_name = selected_report_name.replace('\\', '/').split('/')[-1]
        normalized_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', '_', normalized_name).strip(' .')
        if normalized_name and not normalized_name.lower().endswith('.html'):
            normalized_name = f'{normalized_name}.html'
        report_file_name = normalized_name or default_report_name
    else:
        report_file_name = default_report_name

    report_file = os.path.join(output_dir, report_file_name)
    if os.path.exists(report_file):
        name_no_ext, ext = os.path.splitext(report_file_name)
        report_file = os.path.join(output_dir, f'{name_no_ext}_{timestamp}{ext or ".html"}')
    return report_file


def _flush_checkpoint_state(
    *,
    enable_checkpoint_recovery: bool,
    checkpoint_path: str,
    collection_fingerprint: str,
    parser_base_url: str,
    selected_total_count: int,
    executed_item_paths: set[str],
    completed: bool,
    last_error: str = "",
) -> None:
    if not (enable_checkpoint_recovery and checkpoint_path):
        return
    payload = {
        "collection_fingerprint": collection_fingerprint,
        "base_url": str(parser_base_url or ""),
        "selected_total_count": selected_total_count,
        "executed_item_paths": sorted(executed_item_paths),
        "completed": bool(completed),
        "last_error": str(last_error or ""),
        "updated_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }
    _save_checkpoint_atomic(checkpoint_path, payload)


def _finalize_checkpoint_state(
    *,
    enable_checkpoint_recovery: bool,
    checkpoint_path: str,
    collection_fingerprint: str,
    parser_base_url: str,
    selected_total_count: int,
    executed_item_paths: set[str],
    execution_error: Optional[Exception],
) -> None:
    if not enable_checkpoint_recovery:
        return
    try:
        _flush_checkpoint_state(
            enable_checkpoint_recovery=enable_checkpoint_recovery,
            checkpoint_path=checkpoint_path,
            collection_fingerprint=collection_fingerprint,
            parser_base_url=parser_base_url,
            selected_total_count=selected_total_count,
            executed_item_paths=executed_item_paths,
            completed=(execution_error is None),
            last_error=str(execution_error or ""),
        )
    except (OSError, IOError, TypeError, ValueError) as exc:
        logger.warning("写入 checkpoint 失败: %s", exc)


def _execute_api_suite_concurrent(
    *,
    apis: List[ApiConfig],
    total_apis_count: int,
    report: PostmanTestReport,
    resolved_token: Optional[str],
    request_timeout: RequestTimeout,
    assertion_strict_mode: bool,
    progress_callback: Optional[ProgressCallback],
    enable_checkpoint_recovery: bool,
    checkpoint_flush_every_n: int,
    checkpoint_path: str,
    collection_fingerprint: str,
    parser_base_url: str,
    selected_total_count: int,
    executed_item_paths: set[str],
    shared_session: SessionLike,
    concurrent_workers: int,
    judgment_config: Optional[Dict[str, Any]] = None,
    variable_context: Optional[object] = None,
) -> Tuple[int, Optional[Exception]]:
    """并发执行路径：基于 BatchScheduler 分批 + ThreadPoolExecutor 批次内并行。"""
    import threading

    execution_error: Optional[Exception] = None
    completed_count = 0
    set_lock = threading.Lock()
    tracker = ConcurrentProgressTracker(total=len(apis), callback=progress_callback)

    scheduler = BatchScheduler(apis)
    batches = scheduler.compute_batches()
    total_batches = len(batches)

    logger.info(
        "并发执行模式：%d 个接口分为 %d 个批次，最大线程数 %d",
        len(apis), total_batches, concurrent_workers,
    )

    def _run_single(api: ApiConfig) -> TestResultRecord:
        executor = PostmanTestExecutor(
            api,
            auth_token=resolved_token,
            session=shared_session,
            request_timeout=request_timeout,
            assertion_strict_mode=assertion_strict_mode,
            judgment_config=judgment_config,
            variable_context=variable_context,  # type: ignore[arg-type]
        )
        executor.start()
        return executor.execute_test()

    try:
        for batch_idx, batch_indices in enumerate(batches):
            batch_apis = [apis[i] for i in batch_indices]

            def _on_done(api: ApiConfig, result: TestResultRecord) -> None:
                nonlocal completed_count
                report.add_result(result)
                data_index = int(api.get("data_index", 0) or 0)
                item_path_key = _checkpoint_key(api.get("item_path"), data_index)
                with set_lock:
                    if item_path_key:
                        executed_item_paths.add(item_path_key)
                    completed_count += 1
                tracker.on_item_done(
                    name=str(api.get('name', '')),
                    method=str(api.get('method', '')),
                    url=str(api.get('url', '')),
                    status=str(result.get('status', '')),
                )

            execute_batch_concurrently(
                batch_apis,
                _run_single,
                max_workers=concurrent_workers,
                on_item_done=_on_done,
            )

            if enable_checkpoint_recovery:
                _flush_checkpoint_state(
                    enable_checkpoint_recovery=enable_checkpoint_recovery,
                    checkpoint_path=checkpoint_path,
                    collection_fingerprint=collection_fingerprint,
                    parser_base_url=parser_base_url,
                    selected_total_count=selected_total_count,
                    executed_item_paths=executed_item_paths,
                    completed=False,
                )

            logger.info("批次 %d/%d 完成，%d 个接口", batch_idx + 1, total_batches, len(batch_apis))

    except Exception as exc:
        execution_error = exc
        logger.exception("并发执行过程中发生中断异常: %s", exc)

    return completed_count, execution_error


def _execute_single_api(
    idx: int,
    total: int,
    api: ApiConfig,
    *,
    report: PostmanTestReport,
    resolved_token: Optional[str],
    request_timeout: RequestTimeout,
    assertion_strict_mode: bool,
    judgment_config: Optional[Dict[str, Any]],
    variable_context: Optional[object],
    shared_session: SessionLike,
    enable_checkpoint_recovery: bool,
    checkpoint_flush_every_n: int,
    checkpoint_path: str,
    collection_fingerprint: str,
    parser_base_url: str,
    selected_total_count: int,
    executed_item_paths: set[str],
    total_apis_count: int,
    progress_callback: Optional[ProgressCallback],
) -> TestResultRecord:
	"""执行单个 API 并将结果写入 report，同时处理 checkpoint 与进度回调。"""
	logger.debug("[%d/%d] 测试: %s (%s %s)", idx, total, api['name'], api['method'], api['url'])

	executor = PostmanTestExecutor(
		api,
		auth_token=resolved_token,
		session=shared_session,
		request_timeout=request_timeout,
		assertion_strict_mode=assertion_strict_mode,
		judgment_config=judgment_config,
		variable_context=variable_context,  # type: ignore[arg-type]
	)
	executor.start()
	result: TestResultRecord = executor.execute_test()
	report.add_result(result)

	data_index = int(api.get("data_index", 0) or 0)
	item_path_key = _checkpoint_key(api.get("item_path"), data_index)
	if item_path_key:
		executed_item_paths.add(item_path_key)
	if enable_checkpoint_recovery and (idx % checkpoint_flush_every_n == 0):
		_flush_checkpoint_state(
			enable_checkpoint_recovery=enable_checkpoint_recovery,
			checkpoint_path=checkpoint_path,
			collection_fingerprint=collection_fingerprint,
			parser_base_url=parser_base_url,
			selected_total_count=selected_total_count,
			executed_item_paths=executed_item_paths,
			completed=False,
		)

	event_payload = {
		'event': 'test.run.executed',
		'api_name': str(api.get('name', '')),
		'method': str(api.get('method', '')),
		'status': str(result.get('status', '')),
		'response_time_ms': int(result.get('response_time_ms', 0) or 0),
	}
	if result['status'] == 'PASSED':
		log_sampled(
			logger,
			logging.INFO,
			"[%d/%d] %s %s → %s",
			idx,
			total,
			api['method'],
			api['name'],
			result['status'],
			sample_rate=PASSED_TEST_LOG_SAMPLE_RATE,
			extra=event_payload,
		)
	else:
		logger.warning("[%d/%d] %s %s → %s", idx, total, api['method'], api['name'], result['status'], extra=event_payload)

	_emit_progress(progress_callback, {
		'stage': 'running',
		'total': total,
		'total_all': total_apis_count,
		'completed': idx,
		'percent': int(idx * 100 / total) if total > 0 else 100,
		'current_name': str(api.get('name', '')),
		'current_method': str(api.get('method', '')),
		'current_url': str(api.get('url', '')),
		'last_status': str(result.get('status', '')),
	})
	return result


def _execute_api_suite(
    *,
    apis: List[ApiConfig],
    total_apis_count: int,
    report: PostmanTestReport,
    resolved_token: Optional[str],
    request_timeout: RequestTimeout,
    assertion_strict_mode: bool,
    progress_callback: Optional[ProgressCallback],
    enable_checkpoint_recovery: bool,
    checkpoint_flush_every_n: int,
    checkpoint_path: str,
    collection_fingerprint: str,
    parser_base_url: str,
    selected_total_count: int,
    executed_item_paths: set[str],
    shared_session: SessionLike,
    judgment_config: Optional[Dict[str, Any]] = None,
    variable_context: Optional[object] = None,
    enable_concurrent: bool = False,
    concurrent_workers: int = 10,
) -> Tuple[int, Optional[Exception]]:
    if enable_concurrent and len(apis) > 1:
        return _execute_api_suite_concurrent(
            apis=apis,
            total_apis_count=total_apis_count,
            report=report,
            resolved_token=resolved_token,
            request_timeout=request_timeout,
            assertion_strict_mode=assertion_strict_mode,
            progress_callback=progress_callback,
            enable_checkpoint_recovery=enable_checkpoint_recovery,
            checkpoint_flush_every_n=checkpoint_flush_every_n,
            checkpoint_path=checkpoint_path,
            collection_fingerprint=collection_fingerprint,
            parser_base_url=parser_base_url,
            selected_total_count=selected_total_count,
            executed_item_paths=executed_item_paths,
            shared_session=shared_session,
            concurrent_workers=concurrent_workers,
            judgment_config=judgment_config,
            variable_context=variable_context,
        )

    execution_error: Optional[Exception] = None
    completed_count = 0
    total = len(apis)

    try:
        for idx, api in enumerate(apis, 1):
            _execute_single_api(
                idx, total, api,
                report=report,
                resolved_token=resolved_token,
                request_timeout=request_timeout,
                assertion_strict_mode=assertion_strict_mode,
                judgment_config=judgment_config,
                variable_context=variable_context,
                shared_session=shared_session,
                enable_checkpoint_recovery=enable_checkpoint_recovery,
                checkpoint_flush_every_n=checkpoint_flush_every_n,
                checkpoint_path=checkpoint_path,
                collection_fingerprint=collection_fingerprint,
                parser_base_url=parser_base_url,
                selected_total_count=selected_total_count,
                executed_item_paths=executed_item_paths,
                total_apis_count=total_apis_count,
                progress_callback=progress_callback,
            )
            completed_count = idx
    except Exception as exc:
        execution_error = exc
        logger.exception("执行过程中发生中断异常，将输出部分成功报告: %s", exc)

    return completed_count, execution_error


def _execute_and_finalize_suite(
    *,
    apis: List[ApiConfig],
    total_apis_count: int,
    report: PostmanTestReport,
    resolved_token: Optional[str],
    request_timeout: RequestTimeout,
    assertion_strict_mode: bool,
    progress_callback: Optional[ProgressCallback],
    enable_checkpoint_recovery: bool,
    checkpoint_flush_every_n: int,
    checkpoint_path: str,
    collection_fingerprint: str,
    parser_base_url: str,
    selected_total_count: int,
    executed_item_paths: set[str],
    shared_session: SessionLike,
    judgment_config: Optional[Dict[str, Any]] = None,
    variable_context: Optional[object] = None,
    enable_concurrent: bool = False,
    concurrent_workers: int = 10,
) -> Tuple[int, Optional[Exception]]:
    completed_count = 0
    execution_error: Optional[Exception] = None
    try:
        completed_count, execution_error = _execute_api_suite(
            apis=apis,
            total_apis_count=total_apis_count,
            report=report,
            resolved_token=resolved_token,
            request_timeout=request_timeout,
            assertion_strict_mode=assertion_strict_mode,
            progress_callback=progress_callback,
            enable_checkpoint_recovery=enable_checkpoint_recovery,
            checkpoint_flush_every_n=checkpoint_flush_every_n,
            checkpoint_path=checkpoint_path,
            collection_fingerprint=collection_fingerprint,
            parser_base_url=parser_base_url,
            selected_total_count=selected_total_count,
            executed_item_paths=executed_item_paths,
            shared_session=shared_session,
            judgment_config=judgment_config,
            variable_context=variable_context,
            enable_concurrent=enable_concurrent,
            concurrent_workers=concurrent_workers,
        )
    finally:
        close_session(shared_session)
        _finalize_checkpoint_state(
            enable_checkpoint_recovery=enable_checkpoint_recovery,
            checkpoint_path=checkpoint_path,
            collection_fingerprint=collection_fingerprint,
            parser_base_url=parser_base_url,
            selected_total_count=selected_total_count,
            executed_item_paths=executed_item_paths,
            execution_error=execution_error,
        )
    return completed_count, execution_error


def _prepare_execution_context(
    *,
    token: Optional[str],
    apis: List[ApiConfig],
    parser: PostmanApiParser,
    postman_file: str,
    source_original_file: Optional[str],
    assertion_strict_mode: bool,
) -> Tuple[Optional[str], PostmanTestReport, RequestTimeout, SessionLike]:
    # 预获取认证 token，并使用统一 runtime context（shared_session + timeout）。
    resolved_token, request_timeout, shared_session = _build_runtime_context(token, apis, parser.base_url)

    # 创建报告对象
    report = _build_report_context(
        parser=parser,
        postman_file=postman_file,
        source_original_file=source_original_file,
        assertion_strict_mode=assertion_strict_mode,
    )

    # 执行测试：所有 API 共享同一 Session，避免每次建立新 TCP 连接。
    logger.info("开始执行测试，共 %d 个接口", len(apis))
    return resolved_token, report, request_timeout, shared_session


def _shallow_copy_api(api: ApiConfig) -> ApiConfig:
    """创建 ApiConfig 浅拷贝，保留 TypedDict 类型。"""
    result: ApiConfig = {}
    for key, value in api.items():
        result[key] = value  # type: ignore[literal-required]
    return result


def _expand_apis_with_data(
    apis: List[ApiConfig],
    data_rows: List[Dict[str, str]],
    data_columns: set[str],
) -> List[ApiConfig]:
    """按数据行展开引用了数据变量的接口。

    - 不包含数据变量的 api 保持 1 份（data_index=0）
    - 包含数据变量的 api 展开为 M 份（每行数据一份）
    """
    from postman_api_tester.utils.variable_substitution import (
        api_references_variables,
        substitute_in_api_config,
    )

    if not data_rows:
        return apis

    expanded: List[ApiConfig] = []
    for api in apis:
        if api_references_variables(api, data_columns):
            for idx, row in enumerate(data_rows):
                new_api = substitute_in_api_config(api, row)
                new_api["data_index"] = idx
                new_api["data_row"] = dict(row)
                expanded.append(new_api)
        else:
            api_copy = _shallow_copy_api(api)
            api_copy["data_index"] = 0
            api_copy["data_row"] = {}
            expanded.append(api_copy)

    logger.info(
        "数据驱动展开: %d 个接口 → %d 个（数据行 %d）",
        len(apis), len(expanded), len(data_rows),
    )
    return expanded


def _prepare_execution_apis(
    *,
    postman_file: str,
    selected_item_paths: Optional[List[List[int]]],
    base_url: Optional[str],
    data_rows: Optional[List[Dict[str, str]]] = None,
    data_columns: Optional[set[str]] = None,
) -> Tuple[PostmanApiParser, List[ApiConfig], int, int]:
    parser, apis, total_apis_count = _parse_collection_apis(postman_file)

    apis, selected_path_set = _filter_selected_apis(apis, selected_item_paths)
    _apply_base_url_override(parser, apis, base_url)

    if data_rows and data_columns:
        apis = _expand_apis_with_data(apis, data_rows, data_columns)

    selected_total_count = len(apis)
    _log_execution_scope(
        current_count=selected_total_count,
        total_apis_count=total_apis_count,
        parser_base_url=parser.base_url,
        selected_path_set=selected_path_set,
    )
    return parser, apis, total_apis_count, selected_total_count


def _prepare_runtime_settings(
    token: Optional[str],
    base_url: Optional[str],
    output_dir: Optional[str],
) -> Tuple[
    Optional[str],
    Optional[str],
    str,
    bool,
    int,
    str,
    bool,
]:
    (
        token,
        base_url,
        output_dir,
        enable_checkpoint_recovery,
        checkpoint_flush_every_n,
        checkpoint_dir,
        assertion_strict_mode,
    ) = _resolve_runtime_config(token, base_url, output_dir)

    output_dir = _resolve_output_dir(output_dir)
    _validate_base_url(base_url)

    return (
        token,
        base_url,
        output_dir,
        enable_checkpoint_recovery,
        checkpoint_flush_every_n,
        checkpoint_dir,
        assertion_strict_mode,
    )


def _prepare_checkpoint_and_progress(
    *,
    enable_checkpoint_recovery: bool,
    output_dir: str,
    postman_file: str,
    parser_base_url: str,
    selected_item_paths: Optional[List[List[int]]],
    apis: List[ApiConfig],
    checkpoint_dir: str,
    progress_callback: Optional[ProgressCallback],
    total_apis_count: int,
    data_file: str = "",
) -> Tuple[str, str, set[str], List[ApiConfig]]:
    checkpoint_path, collection_fingerprint, executed_item_paths, apis = _resolve_checkpoint_execution_apis(
        enable_checkpoint_recovery=enable_checkpoint_recovery,
        output_dir=output_dir,
        postman_file=postman_file,
        parser_base_url=parser_base_url,
        selected_item_paths=selected_item_paths,
        apis=apis,
        checkpoint_dir=checkpoint_dir,
        data_file=data_file,
    )

    _emit_start_progress(
        progress_callback,
        current_total=len(apis),
        total_apis_count=total_apis_count,
    )
    return checkpoint_path, collection_fingerprint, executed_item_paths, apis


def _build_report_context(
    parser: PostmanApiParser,
    postman_file: str,
    source_original_file: Optional[str],
    assertion_strict_mode: bool,
) -> PostmanTestReport:
    from postman_api_tester.postman_api_tester import PostmanTestReport
    report = PostmanTestReport()
    raw_info = parser.data.get('info') if isinstance(parser.data, dict) else None
    report.collection_name = str(raw_info.get('name', '') or '') if isinstance(raw_info, dict) else ''
    report.source_file = os.path.abspath(postman_file)
    report.source_original_file = str(source_original_file or '').strip()
    report.base_url = parser.base_url
    report.assertion_strict_mode = assertion_strict_mode
    return report


def _set_report_execution_outcome(report: PostmanTestReport, execution_error: Optional[Exception]) -> None:
    report.execution_mode = 'partial' if execution_error is not None else 'full'
    report.interrupted = execution_error is not None
    report.interrupt_reason = str(execution_error or '')


def _emit_finish_progress(
    progress_callback: Optional[ProgressCallback],
    *,
    execution_error: Optional[Exception],
    completed_count: int,
    current_total: int,
    total_apis_count: int,
) -> None:
    _emit_progress(progress_callback, {
        'stage': 'finished' if execution_error is None else 'partial',
        'total': current_total,
        'total_all': total_apis_count,
        'completed': completed_count,
        'percent': int(completed_count * 100 / current_total) if current_total > 0 else 100,
        'message': '执行完成' if execution_error is None else f'执行中断，已生成部分报告: {execution_error}',
    })


def _generate_and_log_report(
    report: PostmanTestReport,
    *,
    output_dir: str,
    report_name: Optional[str],
    results_per_page: int,
    execution_error: Optional[Exception],
) -> str:
    logger.info("\n生成测试报告...")
    report.generate_summary()

    report_file = _resolve_report_file_path(output_dir, report_name)
    HtmlReporter.generate_html_report(report, report_file, results_per_page=results_per_page)
    logger.info("HTML 报告已保存: %s", report_file)
    logger.info("报告元数据已保存: %s", report.generated_meta_file)
    if execution_error is not None:
        logger.warning("本次报告为部分成功报告，原因: %s", execution_error)
    return report_file


def _complete_report_output(
    report: PostmanTestReport,
    *,
    progress_callback: Optional[ProgressCallback],
    execution_error: Optional[Exception],
    completed_count: int,
    current_total: int,
    total_apis_count: int,
    output_dir: str,
    report_name: Optional[str],
    results_per_page: int,
) -> None:
    _set_report_execution_outcome(report, execution_error)
    _emit_finish_progress(
        progress_callback,
        execution_error=execution_error,
        completed_count=completed_count,
        current_total=current_total,
        total_apis_count=total_apis_count,
    )
    _generate_and_log_report(
        report,
        output_dir=output_dir,
        report_name=report_name,
        results_per_page=results_per_page,
        execution_error=execution_error,
    )
    HtmlReporter.print_console_report(report)
