"""report_junit_service 单元测试。"""

import xml.etree.ElementTree as ET

from postman_api_tester.services.report_junit_service import (
    _parse_duration_to_seconds,
    build_junit_xml,
)


class TestParseDurationToSeconds:
    """_parse_duration_to_seconds 测试。"""

    def test_seconds_with_suffix(self) -> None:
        """带 s 后缀的秒数。"""
        assert _parse_duration_to_seconds("10s") == 10.0

    def test_seconds_without_suffix(self) -> None:
        """纯数字秒数。"""
        assert _parse_duration_to_seconds("5.5") == 5.5

    def test_with_whitespace(self) -> None:
        """带空白字符。"""
        assert _parse_duration_to_seconds("  3.2s  ") == 3.2

    def test_invalid_returns_zero(self) -> None:
        """无效输入返回 0。"""
        assert _parse_duration_to_seconds("invalid") == 0.0

    def test_empty_returns_zero(self) -> None:
        """空字符串返回 0。"""
        assert _parse_duration_to_seconds("") == 0.0

    def test_none_returns_zero(self) -> None:
        """None 返回 0。"""
        assert _parse_duration_to_seconds(None) == 0.0  # type: ignore[arg-type]


class TestBuildJunitXml:
    """build_junit_xml 测试。"""

    def test_empty_report(self) -> None:
        """空报告生成有效 XML。"""
        report = {"summary": {}, "results": [], "report_name": "test"}
        xml_str = build_junit_xml(report)
        root = ET.fromstring(xml_str)
        assert root.tag == "testsuite"
        assert root.get("name") == "test"
        assert root.get("tests") == "0"

    def test_summary_attributes(self) -> None:
        """summary 属性正确映射。"""
        report = {
            "summary": {
                "total": 10,
                "failed": 2,
                "error": 1,
                "duration": "5.5s",
                "start_time": "2026-06-16T10:00:00",
            },
            "results": [],
            "report_name": "my_report",
        }
        xml_str = build_junit_xml(report)
        root = ET.fromstring(xml_str)
        assert root.get("tests") == "10"
        assert root.get("failures") == "2"
        assert root.get("errors") == "1"
        assert root.get("time") == "5.500"
        assert root.get("timestamp") == "2026-06-16T10:00:00"

    def test_passed_testcase(self) -> None:
        """成功用例无 failure/error 子元素。"""
        report = {
            "summary": {"total": 1},
            "results": [{"name": "test1", "status": "PASSED", "response_time_ms": 100}],
            "report_name": "test",
        }
        xml_str = build_junit_xml(report)
        root = ET.fromstring(xml_str)
        tc = root.find("testcase")
        assert tc is not None
        assert tc.get("name") == "test1"
        assert tc.find("failure") is None
        assert tc.find("error") is None

    def test_failed_testcase(self) -> None:
        """失败用例包含 failure 子元素。"""
        report = {
            "summary": {"total": 1, "failed": 1},
            "results": [{"name": "test_fail", "status": "FAILED", "message": "assertion error", "response_time_ms": 50}],
            "report_name": "test",
        }
        xml_str = build_junit_xml(report)
        root = ET.fromstring(xml_str)
        tc = root.find("testcase")
        assert tc is not None
        failure = tc.find("failure")
        assert failure is not None
        assert failure.get("message") == "assertion error"

    def test_error_testcase(self) -> None:
        """错误用例包含 error 子元素。"""
        report = {
            "summary": {"total": 1, "error": 1},
            "results": [{"name": "test_err", "status": "ERROR", "message": "connection timeout", "response_time_ms": 0}],
            "report_name": "test",
        }
        xml_str = build_junit_xml(report)
        root = ET.fromstring(xml_str)
        tc = root.find("testcase")
        assert tc is not None
        error_el = tc.find("error")
        assert error_el is not None
        assert error_el.get("message") == "connection timeout"

    def test_classname_with_folder(self) -> None:
        """有 folder 时 classname 为 folder.name。"""
        report = {
            "summary": {"total": 1},
            "results": [{"name": "test1", "folder": "group1", "status": "PASSED", "response_time_ms": 10}],
            "report_name": "test",
        }
        xml_str = build_junit_xml(report)
        root = ET.fromstring(xml_str)
        tc = root.find("testcase")
        assert tc is not None
        assert tc.get("classname") == "group1.test1"

    def test_classname_without_folder(self) -> None:
        """无 folder 时 classname 为 name。"""
        report = {
            "summary": {"total": 1},
            "results": [{"name": "test1", "status": "PASSED", "response_time_ms": 10}],
            "report_name": "test",
        }
        xml_str = build_junit_xml(report)
        root = ET.fromstring(xml_str)
        tc = root.find("testcase")
        assert tc is not None
        assert tc.get("classname") == "test1"

    def test_xml_declaration(self) -> None:
        """输出包含 XML 声明。"""
        report = {"summary": {}, "results": [], "report_name": "test"}
        xml_str = build_junit_xml(report)
        assert xml_str.startswith("<?xml")

    def test_escapes_special_characters(self) -> None:
        """特殊字符被 XML 转义。"""
        report = {
            "summary": {"total": 1},
            "results": [{"name": "test <>&", "status": "FAILED", "message": "err <msg>", "response_time_ms": 10}],
            "report_name": "test & report",
        }
        xml_str = build_junit_xml(report)
        assert "&amp;" in xml_str
        assert "&lt;" in xml_str or "&" in xml_str
