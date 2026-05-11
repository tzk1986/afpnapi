import json
from typing import Any, Dict, List, Optional, Tuple


DB_FEEDBACK_RULES: List[Tuple[str, List[str], str, str]] = [
    (
        "db_connection",
        [
            "communications link failure",
            "connection refused",
            "connection reset",
            "connect timed out",
            "read timed out",
            "could not connect",
            "数据库连接",
            "连接数据库",
            "连接超时",
            "too many connections",
        ],
        "数据库连接异常",
        "疑似数据库连接或网络链路问题，建议先检查数据库可达性、连接串、网络与防火墙策略。",
    ),
    (
        "db_auth",
        [
            "access denied",
            "authentication failed",
            "invalid username/password",
            "login failed",
            "密码错误",
            "用户不存在",
            "账号锁定",
        ],
        "数据库认证异常",
        "疑似数据库账号或权限问题，建议核对用户名、密码、授权及白名单策略。",
    ),
    (
        "db_sql_compat",
        [
            "sqlsyntaxerrorexception",
            "you have an error in your sql syntax",
            "syntax error",
            "invalid identifier",
            "unknown column",
            "function does not exist",
            "unsupported",
            "not support",
            "语法错误",
            "函数不存在",
            "字段不存在",
        ],
        "SQL兼容性异常",
        "疑似MySQL切换到国产数据库后的SQL兼容差异，建议优先排查方言、函数和关键字差异。",
    ),
    (
        "db_object",
        [
            "doesn't exist",
            "relation does not exist",
            "schema",
            "对象不存在",
            "表不存在",
            "视图不存在",
        ],
        "数据库对象异常",
        "疑似库表或schema映射问题，建议检查迁移后的对象名、schema和大小写规则。",
    ),
    (
        "db_charset",
        [
            "collation",
            "incorrect string value",
            "character set",
            "乱码",
            "编码",
        ],
        "字符集/排序规则异常",
        "疑似字符集或排序规则不一致，建议核对数据库编码、连接编码与字段字符集配置。",
    ),
    (
        "db_type",
        [
            "data truncation",
            "out of range",
            "invalid number",
            "invalid datetime",
            "日期格式",
            "数值溢出",
            "类型转换",
        ],
        "数据类型兼容异常",
        "疑似字段类型或数据精度兼容问题，建议重点检查日期、数值、布尔和空值处理。",
    ),
]


def build_db_feedback(
    status: str,
    status_code: Optional[int],
    response_message: str,
    err_code: str,
    response_body: Any,
) -> Dict[str, Any]:
    """识别数据库迁移相关异常并返回结构化建议。"""
    if status == 'PASSED':
        return {}

    if isinstance(response_body, (dict, list)):
        try:
            body_text = json.dumps(response_body, ensure_ascii=False)
        except (TypeError, ValueError):
            body_text = str(response_body)
    else:
        body_text = str(response_body or '')

    diagnosis_text = " | ".join([
        str(response_message or ''),
        str(err_code or ''),
        body_text,
        str(status_code or ''),
    ]).lower()

    for category, patterns, title, suggestion in DB_FEEDBACK_RULES:
        if any(pattern.lower() in diagnosis_text for pattern in patterns):
            return {
                'is_db_related': True,
                'category': category,
                'title': title,
                'suggestion': suggestion,
                'raw_status': status,
                'status_code': status_code,
                'err_code': err_code,
            }

    return {
        'is_db_related': False,
        'category': 'unknown',
        'title': '未识别为典型数据库异常',
        'suggestion': '建议结合应用日志确认是否为数据库迁移导致；若重复出现可补充识别关键词。',
        'raw_status': status,
        'status_code': status_code,
        'err_code': err_code,
    }
