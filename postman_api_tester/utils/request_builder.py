"""Request builder utilities for HTTP request assembly."""

import json
from typing import Any, Dict, List
from urllib.parse import urlencode

from postman_api_tester.runtime_utils import merge_url_with_params as _merge_url_with_params


def set_request_url(request_obj: Dict[str, Any], raw_url: str, params: Dict[str, Any]) -> None:
    merged_url = _merge_url_with_params(raw_url, params)
    url_obj = request_obj.get("url")
    if isinstance(url_obj, dict):
        request_obj["url"]["raw"] = merged_url
        request_obj["url"]["query"] = [
            {"key": str(key), "value": "" if value is None else str(value)}
            for key, value in (params or {}).items()
        ]
    else:
        request_obj["url"] = merged_url


def set_request_headers(request_obj: Dict[str, Any], headers: Dict[str, Any]) -> None:
    request_obj["header"] = [
        {"key": str(key), "value": "" if value is None else str(value)}
        for key, value in (headers or {}).items()
    ]


def normalize_urlencoded_rows(data: Any) -> List[Dict[str, Any]]:
    if isinstance(data, dict) and isinstance(data.get("urlencoded"), list):
        rows = data.get("urlencoded")
    elif isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        rows = [{"key": key, "value": value} for key, value in data.items()]
    else:
        rows = []

    normalized = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = str(row.get("key") or "").strip()
        if not key:
            continue
        value = "" if row.get("value") is None else str(row.get("value"))
        normalized.append({"key": key, "value": value})
    return normalized


def normalize_formdata_rows(data: Any) -> List[Dict[str, Any]]:
    if isinstance(data, dict) and isinstance(data.get("formdata"), list):
        rows = data.get("formdata")
    elif isinstance(data, list):
        rows = data
    else:
        rows = []

    normalized = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = str(row.get("key") or "").strip()
        if not key:
            continue
        row_type = "file" if str(row.get("type") or "text").strip().lower() == "file" else "text"
        item: Dict[str, Any] = {"key": key, "type": row_type}
        if row_type == "file":
            file_name = str(row.get("file_name") or row.get("src") or "").strip()
            if file_name:
                item["src"] = file_name
                item["file_name"] = file_name
        else:
            item["value"] = "" if row.get("value") is None else str(row.get("value"))
        normalized.append(item)
    return normalized


def normalize_graphql_data(data: Any) -> Dict[str, Any]:
    if not isinstance(data, dict):
        return {"query": "", "variables": {}}
    query = str(data.get("query") or "")
    variables_raw = data.get("variables")
    if isinstance(variables_raw, str):
        try:
            variables = json.loads(variables_raw or "{}")
        except Exception as exc:
            raise ValueError(f"GraphQL Variables 必须是合法 JSON: {exc}") from exc
    elif isinstance(variables_raw, dict):
        variables = variables_raw
    else:
        variables = {}
    return {"query": query, "variables": variables}


def infer_body_mode_from_stored_body(body: Any) -> Dict[str, Any] | None:
    if not isinstance(body, dict):
        return None
    manual_mode = str(body.get("__manual_body_mode") or "").strip().lower()
    if manual_mode == "raw":
        return {
            "mode": "raw",
            "data": {
                "raw_language": str(body.get("raw_language") or "json"),
                "raw_content_type": str(body.get("raw_content_type") or "application/json"),
                "raw_content": str(body.get("raw_content") or ""),
            },
        }
    if manual_mode == "urlencoded":
        return {"mode": "urlencoded", "data": {"urlencoded": body.get("urlencoded") or []}}
    if manual_mode == "formdata":
        return {"mode": "formdata", "data": {"formdata": body.get("formdata") or []}}
    if manual_mode == "graphql":
        return {"mode": "graphql", "data": body.get("graphql") or {}}
    if manual_mode == "binary":
        return {"mode": "binary", "data": body.get("binary") or {}}
    if manual_mode == "none":
        return {"mode": "none", "data": None}

    if "formdata" in body:
        return {"mode": "formdata", "data": body}
    if "urlencoded" in body:
        return {"mode": "urlencoded", "data": body}
    if "query" in body and "variables" in body:
        return {"mode": "graphql", "data": body}
    if "file_name" in body and len(body.keys()) <= 3:
        return {"mode": "binary", "data": body}
    return None


def set_request_body(request_obj: Dict[str, Any], body: Any, body_mode: str | None = None, body_data: Any = None) -> None:
    mode = str(body_mode or "legacy").strip().lower()
    data = body_data

    if mode == "legacy":
        inferred = infer_body_mode_from_stored_body(body)
        if inferred:
            mode = str(inferred.get("mode") or "legacy")
            data = inferred.get("data")

    if mode == "none":
        request_obj.pop("body", None)
        return

    if mode == "raw":
        if isinstance(data, dict):
            raw_content = str(data.get("raw_content") or "")
            raw_language = str(data.get("raw_language") or "text").strip().lower() or "text"
        else:
            raw_content = "" if data is None else str(data)
            raw_language = "text"
        request_obj["body"] = {
            "mode": "raw",
            "raw": raw_content,
            "options": {"raw": {"language": raw_language}},
        }
        return

    if mode == "urlencoded":
        rows = normalize_urlencoded_rows(data)
        request_obj["body"] = {
            "mode": "urlencoded",
            "urlencoded": rows,
        }
        return

    if mode == "formdata":
        rows = normalize_formdata_rows(data)
        request_obj["body"] = {
            "mode": "formdata",
            "formdata": rows,
        }
        return

    if mode == "graphql":
        gql = normalize_graphql_data(data)
        request_obj["body"] = {
            "mode": "graphql",
            "graphql": {
                "query": gql["query"],
                "variables": json.dumps(gql["variables"], ensure_ascii=False),
            },
        }
        return

    if mode == "binary":
        file_name = ""
        if isinstance(data, dict):
            file_name = str(data.get("file_name") or data.get("src") or "").strip()
        request_obj["body"] = {
            "mode": "file",
            "file": {"src": file_name or None},
        }
        return

    if isinstance(body, (dict, list)):
        request_obj["body"] = {
            "mode": "raw",
            "raw": json.dumps(body, ensure_ascii=False),
            "options": {"raw": {"language": "json"}},
        }
        return

    request_obj["body"] = {
        "mode": "raw",
        "raw": str(body),
    }


def build_request_kwargs(
    *,
    is_multipart: bool,
    body_mode: str,
    body_data: Any,
    legacy_body: Any,
    headers: Dict[str, Any],
    files_source: Any,
) -> Dict[str, Any]:
    request_kwargs: Dict[str, Any] = {}
    headers_to_send = dict(headers or {})
    normalized_mode = str(body_mode or "legacy").strip().lower() or "legacy"
    normalized_data: Any = body_data
    stored_body: Any = None

    if is_multipart:
        if normalized_mode == "formdata":
            rows = normalize_formdata_rows(body_data)
            data_rows = []
            file_rows = []
            for row in rows:
                key = row["key"]
                row_type = row["type"]
                if row_type == "file":
                    upload_key = str(row.get("upload_key") or "").strip()
                    if not upload_key:
                        upload_key = "upload_0"
                    file_obj = files_source.get(upload_key) if files_source is not None else None
                    if file_obj and str(file_obj.filename or "").strip():
                        file_rows.append((key, (file_obj.filename, file_obj.stream, file_obj.mimetype or "application/octet-stream")))
                        row["file_name"] = str(file_obj.filename or row.get("file_name") or "")
                else:
                    data_rows.append((key, "" if row.get("value") is None else str(row.get("value"))))
            headers_to_send.pop("Content-Type", None)
            request_kwargs["data"] = data_rows
            request_kwargs["files"] = file_rows
            normalized_data = {"formdata": rows}
            stored_body = normalized_data
        elif normalized_mode == "binary":
            upload_key = "upload_0"
            if isinstance(body_data, dict):
                upload_key = str(body_data.get("upload_key") or upload_key).strip() or "upload_0"
            file_obj = files_source.get(upload_key) if files_source is not None else None
            if not file_obj:
                raise ValueError("binary 模式缺少上传文件")
            payload_bytes = file_obj.read()
            request_kwargs["data"] = payload_bytes
            headers_to_send.setdefault("Content-Type", file_obj.mimetype or "application/octet-stream")
            normalized_data = {"file_name": str(file_obj.filename or "")}
            stored_body = normalized_data
        else:
            raise ValueError(f"multipart 请求不支持 body_mode={normalized_mode}")
    else:
        if normalized_mode == "none":
            request_kwargs["data"] = None
            normalized_data = None
            stored_body = None
        elif normalized_mode == "raw":
            raw_content = ""
            raw_language = "text"
            raw_ct = ""
            if isinstance(body_data, dict):
                raw_content = str(body_data.get("raw_content") or "")
                raw_language = str(body_data.get("raw_language") or "text").strip().lower() or "text"
                raw_ct = str(body_data.get("raw_content_type") or "").strip()
            if raw_ct:
                headers_to_send.setdefault("Content-Type", raw_ct)
            request_kwargs["data"] = raw_content
            normalized_data = {
                "raw_language": raw_language,
                "raw_content_type": raw_ct,
                "raw_content": raw_content,
            }
            stored_body = raw_content
        elif normalized_mode == "urlencoded":
            rows = normalize_urlencoded_rows(body_data)
            params_list = [(row["key"], row["value"]) for row in rows]
            request_kwargs["data"] = urlencode(params_list, doseq=True)
            headers_to_send.setdefault("Content-Type", "application/x-www-form-urlencoded")
            normalized_data = {"urlencoded": rows}
            stored_body = {key: value for key, value in params_list}
        elif normalized_mode == "graphql":
            gql = normalize_graphql_data(body_data)
            gql_payload = {"query": gql["query"], "variables": gql["variables"]}
            request_kwargs["json"] = gql_payload
            headers_to_send.setdefault("Content-Type", "application/json")
            normalized_data = gql_payload
            stored_body = gql_payload
        elif normalized_mode == "legacy":
            if legacy_body is not None:
                request_kwargs["json"] = legacy_body
            else:
                request_kwargs["data"] = None
            normalized_data = legacy_body
            stored_body = legacy_body
        else:
            raise ValueError(f"不支持的 body_mode: {normalized_mode}")

    return {
        "request_kwargs": request_kwargs,
        "headers_to_send": headers_to_send,
        "stored_body": stored_body,
        "stored_body_mode": normalized_mode,
        "stored_body_data": normalized_data,
    }

__all__ = [
    "set_request_url",
    "set_request_headers",
    "normalize_urlencoded_rows",
    "normalize_formdata_rows",
    "normalize_graphql_data",
    "infer_body_mode_from_stored_body",
    "set_request_body",
    "build_request_kwargs",
]
