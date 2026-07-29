"""Response parsing helpers."""

"""开发导读：
- 职责：从响应体提取通用 message/err_code 字段，统一错误展示口径。
- 入口：extract_msg_errcode()。
"""

from typing import Any, Dict, List, Tuple


def extract_msg_errcode(body: Any) -> Tuple[str, str]:
	if not isinstance(body, dict):
		return "", ""

	def pick(obj: Dict[str, Any], keys: List[str]) -> str:
		for key in keys:
			val = obj.get(key)
			if val is not None and str(val).strip():
				return str(val).strip()
		return ""

	msg_keys = ["message", "msg", "error_message", "errorMessage", "errMsg"]
	err_keys = ["errCode", "errcode", "errorCode", "error_code", "code"]

	message = pick(body, msg_keys)
	err_code = pick(body, err_keys)

	nested = body.get("data")
	if isinstance(nested, dict):
		if not message:
			message = pick(nested, msg_keys)
		if not err_code:
			err_code = pick(nested, err_keys)

	return message, err_code


__all__ = ["extract_msg_errcode"]
