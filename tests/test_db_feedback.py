"""db_feedback 模块单元测试。

覆盖 build_db_feedback 各类数据库异常模式识别与 PASSED 跳过逻辑。
"""

from typing import Any, Dict, Optional

import pytest

from postman_api_tester.db_feedback import DB_FEEDBACK_RULES, build_db_feedback


class TestBuildDbFeedbackPassed:
	"""PASSED 状态应直接返回空字典。"""

	def test_passed_returns_empty(self) -> None:
		result = build_db_feedback("PASSED", 200, "", "", "")
		assert result == {}

	def test_passed_ignores_error_patterns(self) -> None:
		result = build_db_feedback("PASSED", 200, "connection refused", "", "")
		assert result == {}


class TestBuildDbFeedbackConnectionPatterns:
	"""db_connection 类别模式匹配测试。"""

	def test_communications_link_failure(self) -> None:
		result = build_db_feedback("FAILED", 500, "Communications link failure", "", "")
		assert result["is_db_related"] is True
		assert result["category"] == "db_connection"

	def test_connection_refused(self) -> None:
		result = build_db_feedback("FAILED", 500, "Connection refused", "", "")
		assert result["category"] == "db_connection"

	def test_connection_reset(self) -> None:
		result = build_db_feedback("ERROR", None, "Connection reset by peer", "", "")
		assert result["category"] == "db_connection"

	def test_connect_timed_out(self) -> None:
		result = build_db_feedback("FAILED", 504, "Connect timed out", "", "")
		assert result["category"] == "db_connection"

	def test_too_many_connections(self) -> None:
		result = build_db_feedback("FAILED", 500, "Too many connections", "", "")
		assert result["category"] == "db_connection"

	def test_chinese_connection_error(self) -> None:
		result = build_db_feedback("FAILED", 500, "数据库连接失败", "", "")
		assert result["category"] == "db_connection"


class TestBuildDbFeedbackAuthPatterns:
	"""db_auth 类别模式匹配测试。"""

	def test_access_denied(self) -> None:
		result = build_db_feedback("FAILED", 403, "Access denied for user 'root'", "", "")
		assert result["is_db_related"] is True
		assert result["category"] == "db_auth"

	def test_authentication_failed(self) -> None:
		result = build_db_feedback("FAILED", 401, "Authentication failed", "", "")
		assert result["category"] == "db_auth"

	def test_chinese_password_error(self) -> None:
		result = build_db_feedback("FAILED", 403, "密码错误", "", "")
		assert result["category"] == "db_auth"


class TestBuildDbFeedbackSqlCompatPatterns:
	"""db_sql_compat 类别模式匹配测试。"""

	def test_sqlsyntaxerrorexception(self) -> None:
		result = build_db_feedback("FAILED", 500, "SQLSyntaxErrorException", "", "")
		assert result["category"] == "db_sql_compat"

	def test_sql_syntax_error(self) -> None:
		result = build_db_feedback("FAILED", 500, "You have an error in your SQL syntax", "", "")
		assert result["category"] == "db_sql_compat"

	def test_unknown_column(self) -> None:
		result = build_db_feedback("FAILED", 500, "Unknown column 'foo' in 'field list'", "", "")
		assert result["category"] == "db_sql_compat"

	def test_chinese_syntax_error(self) -> None:
		result = build_db_feedback("FAILED", 500, "语法错误", "", "")
		assert result["category"] == "db_sql_compat"


class TestBuildDbFeedbackObjectPatterns:
	"""db_object 类别模式匹配测试。"""

	def test_doesnt_exist(self) -> None:
		result = build_db_feedback("FAILED", 500, "Table 'users' doesn't exist", "", "")
		assert result["category"] == "db_object"

	def test_relation_does_not_exist(self) -> None:
		result = build_db_feedback("FAILED", 500, "relation does not exist", "", "")
		assert result["category"] == "db_object"

	def test_chinese_table_not_exist(self) -> None:
		result = build_db_feedback("FAILED", 500, "表不存在", "", "")
		assert result["category"] == "db_object"


class TestBuildDbFeedbackCharsetPatterns:
	"""db_charset 类别模式匹配测试。"""

	def test_collation(self) -> None:
		result = build_db_feedback("FAILED", 500, "Illegal mix of collations", "", "")
		assert result["category"] == "db_charset"

	def test_incorrect_string_value(self) -> None:
		result = build_db_feedback("FAILED", 500, "Incorrect string value: '\\xF0\\x9F'", "", "")
		assert result["category"] == "db_charset"

	def test_chinese_encoding_error(self) -> None:
		result = build_db_feedback("FAILED", 500, "编码不匹配", "", "")
		assert result["category"] == "db_charset"


class TestBuildDbFeedbackTypePatterns:
	"""db_type 类别模式匹配测试。"""

	def test_data_truncation(self) -> None:
		result = build_db_feedback("FAILED", 500, "Data truncation: out of range value", "", "")
		assert result["category"] == "db_type"

	def test_out_of_range(self) -> None:
		result = build_db_feedback("FAILED", 500, "Out of range value for column 'id'", "", "")
		assert result["category"] == "db_type"

	def test_chinese_date_format(self) -> None:
		result = build_db_feedback("FAILED", 500, "日期格式不正确", "", "")
		assert result["category"] == "db_type"


class TestBuildDbFeedbackNoMatch:
	"""无匹配模式时返回非数据库相关的默认反馈。"""

	def test_unknown_category(self) -> None:
		result = build_db_feedback("FAILED", 500, "some random error", "", "")
		assert result["is_db_related"] is False
		assert result["category"] == "unknown"
		assert "raw_status" in result
		assert result["raw_status"] == "FAILED"

	def test_empty_message(self) -> None:
		result = build_db_feedback("ERROR", None, "", "", "")
		assert result["is_db_related"] is False


class TestBuildDbFeedbackResponseBody:
	"""response_body 不同类型处理测试。"""

	def test_dict_body_searched(self) -> None:
		result = build_db_feedback("FAILED", 500, "", "", {"error": "Connection refused"})
		assert result["category"] == "db_connection"

	def test_list_body_searched(self) -> None:
		result = build_db_feedback("FAILED", 500, "", "", ["Access denied for user"])
		assert result["category"] == "db_auth"

	def test_string_body_searched(self) -> None:
		result = build_db_feedback("FAILED", 500, "", "", "Table doesn't exist")
		assert result["category"] == "db_object"

	def test_none_body(self) -> None:
		result = build_db_feedback("FAILED", 500, "connection reset", "", None)
		assert result["category"] == "db_connection"


class TestBuildDbFeedbackErrCode:
	"""err_code 字段也参与模式匹配。"""

	def test_err_code_matched(self) -> None:
		result = build_db_feedback("FAILED", 500, "", "SQLSYNTAXERROREXCEPTION", "")
		assert result["category"] == "db_sql_compat"


class TestBuildDbFeedbackReturnStructure:
	"""返回值结构完整性测试。"""

	def test_db_related_fields(self) -> None:
		result = build_db_feedback("FAILED", 500, "connection refused", "ERR_001", "")
		assert set(result.keys()) == {"is_db_related", "category", "title", "suggestion", "raw_status", "status_code", "err_code"}
		assert result["status_code"] == 500
		assert result["err_code"] == "ERR_001"

	def test_not_db_related_fields(self) -> None:
		result = build_db_feedback("FAILED", 404, "not found", "", "")
		assert set(result.keys()) == {"is_db_related", "category", "title", "suggestion", "raw_status", "status_code", "err_code"}


class TestDbFeedbackRulesStructure:
	"""DB_FEEDBACK_RULES 常量结构测试。"""

	def test_rules_not_empty(self) -> None:
		assert len(DB_FEEDBACK_RULES) > 0

	def test_each_rule_has_four_elements(self) -> None:
		for rule in DB_FEEDBACK_RULES:
			assert len(rule) == 4
			category, patterns, title, suggestion = rule
			assert isinstance(category, str)
			assert isinstance(patterns, list)
			assert len(patterns) > 0
			assert isinstance(title, str)
			assert isinstance(suggestion, str)
