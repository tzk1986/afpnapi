"""Tests for utils/response_parser.py — 覆盖 extract_msg_errcode() 的全部路径。"""

from __future__ import annotations

import unittest

from postman_api_tester.utils.response_parser import extract_msg_errcode


class TestExtractMsgErrcode(unittest.TestCase):

    def test_non_dict_body_returns_empty(self) -> None:
        assert extract_msg_errcode("bad") == ("", "")
        assert extract_msg_errcode(None) == ("", "")
        assert extract_msg_errcode(42) == ("", "")
        assert extract_msg_errcode([]) == ("", "")

    def test_empty_dict(self) -> None:
        assert extract_msg_errcode({}) == ("", "")

    def test_message_key_at_top_level(self) -> None:
        assert extract_msg_errcode({"message": "ok"}) == ("ok", "")

    def test_msg_key_at_top_level(self) -> None:
        assert extract_msg_errcode({"msg": "success"}) == ("success", "")

    def test_error_message_key(self) -> None:
        assert extract_msg_errcode({"error_message": "bad request"}) == ("bad request", "")

    def test_error_message_camel_case(self) -> None:
        assert extract_msg_errcode({"errorMessage": "not found"}) == ("not found", "")

    def test_err_msg_key(self) -> None:
        assert extract_msg_errcode({"errMsg": "timeout"}) == ("timeout", "")

    def test_err_code_key_at_top_level(self) -> None:
        assert extract_msg_errcode({"errCode": "0"}) == ("", "0")

    def test_errcode_lowercase_key(self) -> None:
        assert extract_msg_errcode({"errcode": "1001"}) == ("", "1001")

    def test_error_code_key(self) -> None:
        assert extract_msg_errcode({"errorCode": "E001"}) == ("", "E001")

    def test_error_code_snake_case_key(self) -> None:
        assert extract_msg_errcode({"error_code": "500"}) == ("", "500")

    def test_code_key(self) -> None:
        assert extract_msg_errcode({"code": "200"}) == ("", "200")

    def test_both_message_and_errcode(self) -> None:
        msg, code = extract_msg_errcode({"message": "success", "errCode": "0"})
        assert msg == "success"
        assert code == "0"

    def test_nested_data_message(self) -> None:
        body = {"data": {"message": "nested ok"}}
        msg, code = extract_msg_errcode(body)
        assert msg == "nested ok"

    def test_nested_data_errcode(self) -> None:
        body = {"data": {"errCode": "200"}}
        msg, code = extract_msg_errcode(body)
        assert code == "200"

    def test_top_level_takes_priority_over_nested(self) -> None:
        body = {"message": "top", "data": {"message": "nested"}}
        msg, _ = extract_msg_errcode(body)
        assert msg == "top"

    def test_data_not_dict_ignored(self) -> None:
        body = {"message": "ok", "data": "not-dict"}
        msg, code = extract_msg_errcode(body)
        assert msg == "ok"
        assert code == ""

    def test_whitespace_only_value_treated_as_empty(self) -> None:
        body = {"message": "   ", "msg": "real"}
        msg, _ = extract_msg_errcode(body)
        assert msg == "real"

    def test_none_value_skipped(self) -> None:
        body = {"message": None, "msg": "fallback"}
        msg, _ = extract_msg_errcode(body)
        assert msg == "fallback"

    def test_integer_value_coerced_to_string(self) -> None:
        body = {"errCode": 0, "message": "ok"}
        msg, code = extract_msg_errcode(body)
        assert msg == "ok"
        assert code == "0"

    def test_priority_order_message_keys(self) -> None:
        body = {"msg": "second", "message": "first"}
        msg, _ = extract_msg_errcode(body)
        assert msg == "first"

    def test_priority_order_err_keys(self) -> None:
        body = {"errcode": "second", "errCode": "first"}
        _, code = extract_msg_errcode(body)
        assert code == "first"


if __name__ == "__main__":
    unittest.main()
