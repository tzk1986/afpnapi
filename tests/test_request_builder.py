"""Tests for utils/request_builder.py — 覆盖 8 个公开函数，正常路径与边界路径。"""

from __future__ import annotations

import json
import unittest
from typing import Any, Dict

from postman_api_tester.utils.request_builder import (
    build_request_kwargs,
    infer_body_mode_from_stored_body,
    normalize_formdata_rows,
    normalize_graphql_data,
    normalize_urlencoded_rows,
    set_request_body,
    set_request_headers,
    set_request_url,
)


# ---------------------------------------------------------------------------
# set_request_url
# ---------------------------------------------------------------------------

class TestSetRequestUrl(unittest.TestCase):

    def test_url_is_dict_updates_raw_and_query(self) -> None:
        req: Dict[str, Any] = {"url": {"raw": "http://old.com", "query": []}}
        set_request_url(req, "http://example.com/api", {"page": "1", "size": "20"})
        assert req["url"]["raw"] == "http://example.com/api?page=1&size=20" or \
               "example.com" in req["url"]["raw"]
        assert isinstance(req["url"]["query"], list)

    def test_url_is_string_replaced(self) -> None:
        req: Dict[str, Any] = {"url": "http://old.com"}
        set_request_url(req, "http://example.com", {"key": "val"})
        assert "example.com" in str(req["url"])

    def test_empty_params(self) -> None:
        req: Dict[str, Any] = {"url": {"raw": "", "query": []}}
        set_request_url(req, "http://example.com", {})
        assert req["url"]["raw"] == "http://example.com"
        assert req["url"]["query"] == []

    def test_none_value_in_params_becomes_empty_string(self) -> None:
        req: Dict[str, Any] = {"url": {"raw": "", "query": []}}
        set_request_url(req, "http://example.com", {"key": None})
        query = req["url"]["query"]
        assert any(row["key"] == "key" and row["value"] == "" for row in query)


# ---------------------------------------------------------------------------
# set_request_headers
# ---------------------------------------------------------------------------

class TestSetRequestHeaders(unittest.TestCase):

    def test_sets_header_list(self) -> None:
        req: Dict[str, Any] = {}
        set_request_headers(req, {"Authorization": "Bearer xyz", "Accept": "application/json"})
        assert len(req["header"]) == 2
        keys = {row["key"] for row in req["header"]}
        assert "Authorization" in keys

    def test_empty_headers(self) -> None:
        req: Dict[str, Any] = {}
        set_request_headers(req, {})
        assert req["header"] == []

    def test_none_value_becomes_empty_string(self) -> None:
        req: Dict[str, Any] = {}
        set_request_headers(req, {"X-Key": None})
        assert req["header"][0]["value"] == ""

    def test_none_headers_input(self) -> None:
        req: Dict[str, Any] = {}
        set_request_headers(req, None)
        assert req["header"] == []


# ---------------------------------------------------------------------------
# normalize_urlencoded_rows
# ---------------------------------------------------------------------------

class TestNormalizeUrlencodedRows(unittest.TestCase):

    def test_dict_with_urlencoded_key(self) -> None:
        data = {"urlencoded": [{"key": "name", "value": "tom"}]}
        result = normalize_urlencoded_rows(data)
        assert result == [{"key": "name", "value": "tom"}]

    def test_plain_list(self) -> None:
        data = [{"key": "a", "value": "1"}, {"key": "b", "value": "2"}]
        result = normalize_urlencoded_rows(data)
        assert len(result) == 2

    def test_dict_without_urlencoded_key_becomes_kv_pairs(self) -> None:
        data = {"x": "1", "y": "2"}
        result = normalize_urlencoded_rows(data)
        keys = {row["key"] for row in result}
        assert "x" in keys and "y" in keys

    def test_skips_rows_with_empty_key(self) -> None:
        data = [{"key": "", "value": "bad"}, {"key": "good", "value": "ok"}]
        result = normalize_urlencoded_rows(data)
        assert len(result) == 1
        assert result[0]["key"] == "good"

    def test_skips_non_dict_rows(self) -> None:
        data = ["bad", {"key": "good", "value": "ok"}]
        result = normalize_urlencoded_rows(data)
        assert len(result) == 1

    def test_none_value_becomes_empty_string(self) -> None:
        data = [{"key": "k", "value": None}]
        result = normalize_urlencoded_rows(data)
        assert result[0]["value"] == ""

    def test_invalid_input_returns_empty(self) -> None:
        assert normalize_urlencoded_rows("bad") == []
        assert normalize_urlencoded_rows(None) == []
        assert normalize_urlencoded_rows(42) == []


# ---------------------------------------------------------------------------
# normalize_formdata_rows
# ---------------------------------------------------------------------------

class TestNormalizeFormdataRows(unittest.TestCase):

    def test_dict_with_formdata_key(self) -> None:
        data = {"formdata": [{"key": "file", "type": "file", "file_name": "a.txt"}]}
        result = normalize_formdata_rows(data)
        assert result[0]["type"] == "file"
        assert result[0]["src"] == "a.txt"

    def test_text_row(self) -> None:
        data = [{"key": "name", "type": "text", "value": "tom"}]
        result = normalize_formdata_rows(data)
        assert result[0]["type"] == "text"
        assert result[0]["value"] == "tom"

    def test_file_row_without_file_name(self) -> None:
        data = [{"key": "f", "type": "file"}]
        result = normalize_formdata_rows(data)
        assert result[0]["type"] == "file"
        assert "src" not in result[0]

    def test_type_defaults_to_text(self) -> None:
        data = [{"key": "name", "value": "tom"}]
        result = normalize_formdata_rows(data)
        assert result[0]["type"] == "text"

    def test_empty_key_skipped(self) -> None:
        data = [{"key": "", "value": "bad"}]
        result = normalize_formdata_rows(data)
        assert result == []

    def test_invalid_input_returns_empty(self) -> None:
        assert normalize_formdata_rows("bad") == []
        assert normalize_formdata_rows(None) == []


# ---------------------------------------------------------------------------
# normalize_graphql_data
# ---------------------------------------------------------------------------

class TestNormalizeGraphqlData(unittest.TestCase):

    def test_valid_dict_with_variables_dict(self) -> None:
        data = {"query": "{ users { id } }", "variables": {"limit": 10}}
        result = normalize_graphql_data(data)
        assert result["query"] == "{ users { id } }"
        assert result["variables"] == {"limit": 10}

    def test_variables_as_json_string(self) -> None:
        data = {"query": "query {}", "variables": '{"limit": 5}'}
        result = normalize_graphql_data(data)
        assert result["variables"] == {"limit": 5}

    def test_invalid_json_string_raises_value_error(self) -> None:
        data = {"query": "query {}", "variables": "not-json"}
        with self.assertRaises(ValueError):
            normalize_graphql_data(data)

    def test_non_dict_input_returns_defaults(self) -> None:
        result = normalize_graphql_data("bad")
        assert result == {"query": "", "variables": {}}

    def test_missing_variables_key(self) -> None:
        result = normalize_graphql_data({"query": "query {}"})
        assert result["variables"] == {}

    def test_none_variables_treated_as_empty(self) -> None:
        result = normalize_graphql_data({"query": "q", "variables": None})
        assert result["variables"] == {}


# ---------------------------------------------------------------------------
# infer_body_mode_from_stored_body
# ---------------------------------------------------------------------------

class TestInferBodyModeFromStoredBody(unittest.TestCase):

    def test_manual_mode_raw(self) -> None:
        body = {"__manual_body_mode": "raw", "raw_content": '{"a":1}', "raw_language": "json"}
        result = infer_body_mode_from_stored_body(body)
        assert result is not None
        assert result["mode"] == "raw"

    def test_manual_mode_urlencoded(self) -> None:
        body = {"__manual_body_mode": "urlencoded", "urlencoded": [{"key": "a"}]}
        result = infer_body_mode_from_stored_body(body)
        assert result is not None
        assert result["mode"] == "urlencoded"

    def test_manual_mode_formdata(self) -> None:
        body = {"__manual_body_mode": "formdata", "formdata": []}
        result = infer_body_mode_from_stored_body(body)
        assert result["mode"] == "formdata"

    def test_manual_mode_graphql(self) -> None:
        body = {"__manual_body_mode": "graphql", "graphql": {"query": "q"}}
        result = infer_body_mode_from_stored_body(body)
        assert result["mode"] == "graphql"

    def test_manual_mode_binary(self) -> None:
        body = {"__manual_body_mode": "binary", "binary": {}}
        result = infer_body_mode_from_stored_body(body)
        assert result["mode"] == "binary"

    def test_manual_mode_none(self) -> None:
        body = {"__manual_body_mode": "none"}
        result = infer_body_mode_from_stored_body(body)
        assert result["mode"] == "none"
        assert result["data"] is None

    def test_infer_formdata_from_structure(self) -> None:
        body = {"formdata": [{"key": "f"}]}
        result = infer_body_mode_from_stored_body(body)
        assert result is not None
        assert result["mode"] == "formdata"

    def test_infer_urlencoded_from_structure(self) -> None:
        body = {"urlencoded": [{"key": "a"}]}
        result = infer_body_mode_from_stored_body(body)
        assert result["mode"] == "urlencoded"

    def test_infer_graphql_from_structure(self) -> None:
        body = {"query": "q", "variables": {}}
        result = infer_body_mode_from_stored_body(body)
        assert result["mode"] == "graphql"

    def test_non_dict_returns_none(self) -> None:
        assert infer_body_mode_from_stored_body("bad") is None
        assert infer_body_mode_from_stored_body(None) is None

    def test_unknown_structure_returns_none(self) -> None:
        assert infer_body_mode_from_stored_body({"random_key": 1}) is None


# ---------------------------------------------------------------------------
# set_request_body
# ---------------------------------------------------------------------------

class TestSetRequestBody(unittest.TestCase):

    def test_none_mode_removes_body(self) -> None:
        req: Dict[str, Any] = {"body": {"mode": "raw", "raw": "old"}}
        set_request_body(req, None, body_mode="none")
        assert "body" not in req

    def test_raw_mode_with_dict_data(self) -> None:
        req: Dict[str, Any] = {}
        data = {"raw_content": '{"x": 1}', "raw_language": "json"}
        set_request_body(req, None, body_mode="raw", body_data=data)
        assert req["body"]["mode"] == "raw"
        assert req["body"]["raw"] == '{"x": 1}'
        assert req["body"]["options"]["raw"]["language"] == "json"

    def test_raw_mode_with_string_data(self) -> None:
        req: Dict[str, Any] = {}
        set_request_body(req, None, body_mode="raw", body_data="plain text")
        assert req["body"]["raw"] == "plain text"

    def test_urlencoded_mode(self) -> None:
        req: Dict[str, Any] = {}
        data = [{"key": "name", "value": "tom"}]
        set_request_body(req, None, body_mode="urlencoded", body_data=data)
        assert req["body"]["mode"] == "urlencoded"
        assert len(req["body"]["urlencoded"]) == 1

    def test_formdata_mode(self) -> None:
        req: Dict[str, Any] = {}
        data = [{"key": "f", "type": "file", "file_name": "a.txt"}]
        set_request_body(req, None, body_mode="formdata", body_data=data)
        assert req["body"]["mode"] == "formdata"

    def test_graphql_mode(self) -> None:
        req: Dict[str, Any] = {}
        data = {"query": "{ users }", "variables": {"id": 1}}
        set_request_body(req, None, body_mode="graphql", body_data=data)
        assert req["body"]["mode"] == "graphql"
        gql = req["body"]["graphql"]
        assert gql["query"] == "{ users }"
        assert '"id": 1' in gql["variables"] or '"id":1' in gql["variables"]

    def test_binary_mode(self) -> None:
        req: Dict[str, Any] = {}
        data = {"file_name": "upload.bin"}
        set_request_body(req, None, body_mode="binary", body_data=data)
        assert req["body"]["mode"] == "file"
        assert req["body"]["file"]["src"] == "upload.bin"

    def test_legacy_mode_with_dict_body(self) -> None:
        req: Dict[str, Any] = {}
        body = {"key": "value"}
        set_request_body(req, body, body_mode=None)
        assert req["body"]["mode"] == "raw"
        assert '"key"' in req["body"]["raw"]

    def test_legacy_mode_with_string_body(self) -> None:
        req: Dict[str, Any] = {}
        set_request_body(req, "plain string", body_mode=None)
        assert req["body"]["raw"] == "plain string"


# ---------------------------------------------------------------------------
# build_request_kwargs
# ---------------------------------------------------------------------------

class TestBuildRequestKwargs(unittest.TestCase):

    def _default_kwargs(self, **overrides: Any) -> Dict[str, Any]:
        defaults: Dict[str, Any] = dict(
            is_multipart=False,
            body_mode="none",
            body_data=None,
            legacy_body=None,
            headers={},
            files_source=None,
        )
        defaults.update(overrides)
        return defaults

    def test_none_mode_returns_empty_data(self) -> None:
        result = build_request_kwargs(**self._default_kwargs(body_mode="none"))
        assert result["request_kwargs"]["data"] is None
        assert result["stored_body"] is None

    def test_raw_mode_sets_data_and_content_type(self) -> None:
        body_data = {"raw_content": '{"x":1}', "raw_language": "json", "raw_content_type": "application/json"}
        result = build_request_kwargs(**self._default_kwargs(body_mode="raw", body_data=body_data))
        assert result["request_kwargs"]["data"] == '{"x":1}'
        assert result["headers_to_send"].get("Content-Type") == "application/json"

    def test_urlencoded_mode_encodes_data(self) -> None:
        body_data = [{"key": "a", "value": "1"}, {"key": "b", "value": "2"}]
        result = build_request_kwargs(**self._default_kwargs(body_mode="urlencoded", body_data=body_data))
        assert "a=1" in result["request_kwargs"]["data"]
        assert result["headers_to_send"]["Content-Type"] == "application/x-www-form-urlencoded"

    def test_graphql_mode_sets_json(self) -> None:
        body_data = {"query": "{ ok }", "variables": {}}
        result = build_request_kwargs(**self._default_kwargs(body_mode="graphql", body_data=body_data))
        assert "json" in result["request_kwargs"]
        assert result["request_kwargs"]["json"]["query"] == "{ ok }"

    def test_legacy_mode_with_body(self) -> None:
        result = build_request_kwargs(**self._default_kwargs(body_mode="legacy", legacy_body={"x": 1}))
        assert result["request_kwargs"]["json"] == {"x": 1}

    def test_legacy_mode_without_body(self) -> None:
        result = build_request_kwargs(**self._default_kwargs(body_mode="legacy", legacy_body=None))
        assert result["request_kwargs"]["data"] is None

    def test_invalid_body_mode_raises(self) -> None:
        with self.assertRaises(ValueError):
            build_request_kwargs(**self._default_kwargs(body_mode="unknown_mode"))

    def test_multipart_formdata_separates_files_and_data(self) -> None:
        body_data = [
            {"key": "name", "type": "text", "value": "tom"},
            {"key": "file", "type": "file", "file_name": "a.txt", "upload_key": "upload_0"},
        ]
        file_obj_mock = _make_file_mock("a.txt", b"content", "text/plain")
        result = build_request_kwargs(**self._default_kwargs(
            is_multipart=True, body_mode="formdata", body_data=body_data,
            files_source={"upload_0": file_obj_mock},
        ))
        assert len(result["request_kwargs"]["data"]) == 1
        assert len(result["request_kwargs"]["files"]) == 1
        assert "Content-Type" not in result["headers_to_send"]

    def test_multipart_binary_requires_file(self) -> None:
        with self.assertRaises(ValueError):
            build_request_kwargs(**self._default_kwargs(
                is_multipart=True, body_mode="binary", body_data={"upload_key": "upload_0"},
                files_source={},
            ))

    def test_multipart_with_unsupported_mode_raises(self) -> None:
        with self.assertRaises(ValueError):
            build_request_kwargs(**self._default_kwargs(
                is_multipart=True, body_mode="raw",
            ))

    def test_return_structure(self) -> None:
        result = build_request_kwargs(**self._default_kwargs())
        assert "request_kwargs" in result
        assert "headers_to_send" in result
        assert "stored_body" in result
        assert "stored_body_mode" in result
        assert "stored_body_data" in result


def _make_file_mock(filename: str, content: bytes, mimetype: str) -> Any:
    import io
    mock: Dict[str, Any] = {
        "filename": filename,
        "stream": io.BytesIO(content),
        "mimetype": mimetype,
    }

    class _Mock:
        def __init__(self) -> None:
            self.filename = filename
            self.stream = io.BytesIO(content)
            self.mimetype = mimetype

        def read(self) -> bytes:
            return self.stream.read()

    return _Mock()


if __name__ == "__main__":
    unittest.main()
