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


def compute_summary(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(results)
    passed = sum(1 for r in results if r.get("status") == "PASSED")
    failed = sum(1 for r in results if r.get("status") == "FAILED")
    error = sum(1 for r in results if r.get("status") == "ERROR")
    rate = f"{(passed / total * 100):.2f}%" if total > 0 else "0.00%"
    return {"total": total, "passed": passed, "failed": failed, "error": error, "success_rate": rate}
