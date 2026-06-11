"""可配置结果判定工具。

将 errCode / message / 状态码三维判定逻辑集中管理，
供 executor.py 与 test_proxy_routes.py 共同调用。

优先级：任务级配置 > 集合接口级 x_* > 全局 config > 内置默认值。
"""

from typing import FrozenSet, Optional, Tuple


_DEFAULT_SUCCESS_MESSAGES: FrozenSet[str] = frozenset({"success"})


def parse_success_list(config_value: str) -> FrozenSet[str]:
    """解析逗号分隔的配置值为小写集合。

    >>> parse_success_list("0, 200, ")
    frozenset({'0', '200', ''})
    """
    if not config_value or not config_value.strip():
        return frozenset()
    return frozenset(
        item.strip().lower()
        for item in config_value.split(",")
    )


def evaluate_result_judgment(
    *,
    status_code: int,
    expected_status: int,
    err_code: str,
    response_message: str,
    success_err_codes: Optional[FrozenSet[str]] = None,
    success_messages: Optional[FrozenSet[str]] = None,
    enable_err_code_judgment: bool = False,
    enable_message_judgment: bool = True,
) -> Tuple[bool, str]:
    """评估测试结果是否通过。

    Returns:
        (is_passed, fail_reason)
        - is_passed=True 时 fail_reason 为空字符串
        - is_passed=False 时 fail_reason 描述具体哪个维度不通过
    """
    fail_reasons = []

    status_code_ok = status_code == expected_status
    if not status_code_ok:
        fail_reasons.append(
            f"期望状态码: {expected_status}, 实际: {status_code}"
        )

    err_code_ok = True
    if enable_err_code_judgment:
        codes = success_err_codes if success_err_codes is not None else frozenset()
        normalized_err_code = str(err_code or "").strip().lower()
        err_code_ok = normalized_err_code in codes
        if not err_code_ok:
            display_codes = sorted(codes) if codes else ["(未配置)"]
            fail_reasons.append(
                f"errCode 不满足成功条件(期望为 {display_codes}), 实际返回: {err_code or '(空)'}"
            )

    message_ok = True
    if enable_message_judgment:
        msgs = success_messages if success_messages is not None else _DEFAULT_SUCCESS_MESSAGES
        normalized_msg = str(response_message or "").strip().lower()
        message_ok = (normalized_msg == "") or (normalized_msg in msgs)
        if not message_ok:
            display_msgs = sorted(msgs) if msgs else ["(未配置)"]
            fail_reasons.append(
                f"message 不满足成功条件(期望为 {display_msgs}), 实际返回: {response_message or '(空)'}"
            )

    if fail_reasons:
        return False, "; ".join(fail_reasons)
    return True, ""


def resolve_judgment_params(
    *,
    global_enable_err_code: bool,
    global_success_err_codes: FrozenSet[str],
    global_enable_message: bool,
    global_success_messages: FrozenSet[str],
    item_x_enable_err_code: Optional[bool] = None,
    item_x_success_err_codes: Optional[str] = None,
    item_x_enable_message: Optional[bool] = None,
    item_x_success_messages: Optional[str] = None,
    task_enable_err_code: Optional[bool] = None,
    task_success_err_codes: Optional[str] = None,
    task_enable_message: Optional[bool] = None,
    task_success_messages: Optional[str] = None,
) -> dict:
    """按四层优先级解析最终判定参数。

    优先级：任务级 > 集合接口级 x_* > 全局 config > 内置默认值。

    Returns:
        dict with keys: enable_err_code_judgment, success_err_codes,
                        enable_message_judgment, success_messages
    """
    enable_err = global_enable_err_code
    if item_x_enable_err_code is not None:
        enable_err = item_x_enable_err_code
    if task_enable_err_code is not None:
        enable_err = task_enable_err_code

    err_codes = global_success_err_codes
    if item_x_success_err_codes is not None and str(item_x_success_err_codes).strip():
        err_codes = parse_success_list(str(item_x_success_err_codes))
    if task_success_err_codes is not None and str(task_success_err_codes).strip():
        err_codes = parse_success_list(str(task_success_err_codes))

    enable_msg = global_enable_message
    if item_x_enable_message is not None:
        enable_msg = item_x_enable_message
    if task_enable_message is not None:
        enable_msg = task_enable_message

    msgs = global_success_messages
    if item_x_success_messages is not None and str(item_x_success_messages).strip():
        msgs = parse_success_list(str(item_x_success_messages))
    if task_success_messages is not None and str(task_success_messages).strip():
        msgs = parse_success_list(str(task_success_messages))

    return {
        "enable_err_code_judgment": enable_err,
        "success_err_codes": err_codes,
        "enable_message_judgment": enable_msg,
        "success_messages": msgs,
    }
