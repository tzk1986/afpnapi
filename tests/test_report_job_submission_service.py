"""报告任务提交服务单元测试."""

import re
import pytest
from pathlib import Path
from postman_api_tester.services.report_job_submission_service import (
    sanitize_uploaded_name,
    build_run_postman_job_params,
    build_ad_hoc_job_params,
    build_saved_json_path,
)


class TestSanitizeUploadedName:
    """文件名清洗测试."""

    def test_normal_filename(self) -> None:
        """测试普通文件名保持不变."""
        assert sanitize_uploaded_name("collection.json") == "collection.json"
        assert sanitize_uploaded_name("api-test_v2.yaml") == "api-test_v2.yaml"
        assert sanitize_uploaded_name("My Collection (1).json") == "My Collection (1).json"

    def test_cjk_characters_preserved(self) -> None:
        """测试中日韩字符保留."""
        assert sanitize_uploaded_name("集合.json") == "集合.json"
        assert sanitize_uploaded_name("API测试_ collection.json") == "API测试_ collection.json"
        # 一-鿿 范围的 CJK 统一表意字符应被保留
        assert sanitize_uploaded_name("测试文件.json") == "测试文件.json"

    def test_dangerous_chars_replaced(self) -> None:
        """测试危险字符被替换为下划线."""
        assert sanitize_uploaded_name("file<>name.txt") == "file__name.txt"
        assert sanitize_uploaded_name("path\\to\\file.json") == "path_to_file.json"
        assert sanitize_uploaded_name('file"name.json') == 'file_name.json'
        assert sanitize_uploaded_name("file|name.json") == "file_name.json"
        assert sanitize_uploaded_name("file*name.json") == "file_name.json"
        assert sanitize_uploaded_name("file?name.json") == "file_name.json"
        assert sanitize_uploaded_name("file[name].json") == "file_name_.json"

    def test_brackets_chinese_and_western_preserved(self) -> None:
        """测试中西文括号保留."""
        # 全角括号（）和【】在正则白名单中，被保留
        assert sanitize_uploaded_name("文件（中文）.json") == "文件（中文）.json"
        assert sanitize_uploaded_name("【特殊】.json") == "【特殊】.json"
        # 半角方括号[] 不在白名单中，被替换为下划线
        assert sanitize_uploaded_name("文件[英文].json") == "文件_英文_.json"

    def test_empty_string_fallback(self) -> None:
        """测试空字符串回退到默认值."""
        assert sanitize_uploaded_name("") == "collection.json"

    def test_all_special_chars_fallback(self) -> None:
        """测试全部是危险字符但替换后非空时的行为."""
        # < > 被替换为 _，结果为 "______"，strip('. ') 不处理 _，所以不触发 fallback
        result = sanitize_uploaded_name("<><><>")
        assert result == "______"

    def test_dots_only_triggers_fallback(self) -> None:
        """测试仅有 . 和空格（会被 strip 清空）时触发 fallback."""
        result = sanitize_uploaded_name(". ... .")
        assert result == "collection.json"

    def test_leading_trailing_dots_spaces_stripped(self) -> None:
        """测试首尾的点和空格被去除."""
        assert sanitize_uploaded_name(".  file.json  ") == "file.json"
        assert sanitize_uploaded_name("..file..json..") == "file..json"

    def test_none_input_handled(self) -> None:
        """测试 None 输入被转换为空字符串然后回退."""
        assert sanitize_uploaded_name(None) == "collection.json"

    def test_preserves_unicode_word_chars(self) -> None:
        """测试 Unicode 单词字符（如数字、字母、下划线）被保留."""
        # \w 匹配 [a-zA-Z0-9_]，加上 CJK 范围
        assert sanitize_uploaded_name("test_123.json") == "test_123.json"
        assert sanitize_uploaded_name("文件_123.json") == "文件_123.json"

    def test_multiple_dots_in_name(self) -> None:
        """测试文件名中多个点号的处理."""
        assert sanitize_uploaded_name("my.collection.v2.json") == "my.collection.v2.json"


class TestBuildRunPostmanJobParams:
    """构建 Run Postman 任务参数测试."""

    @pytest.fixture
    def base_params(self):
        """返回基础参数."""
        return {
            "job_id": "job-001",
            "original_name": "test-collection.json",
            "saved_file": "/tmp/saved/test.json",
            "output_dir": "/tmp/output",
            "report_name": "report-001",
            "base_url": "http://localhost:3000",
            "token": "bearer-token-123",
            "selected_item_paths": [[0, 1], [2, 3]],
        }

    def test_all_fields_present(self, base_params) -> None:
        """测试所有字段都存在时的完整结构."""
        result = build_run_postman_job_params(**base_params)
        assert result["id"] == "job-001"
        assert result["status"] == "queued"
        assert result["message"] == "任务已入队，等待执行。"
        assert result["total"] == 0
        assert result["completed"] == 0
        assert result["percent"] == 0
        assert result["current_name"] == ""
        assert result["file_name"] == "test-collection.json"
        assert result["saved_file"] == "/tmp/saved/test.json"
        assert result["output_dir"] == "/tmp/output"
        assert result["report_name"] == "report-001"
        assert result["run_scope"] == "selected"
        assert result["selected_count"] == 2
        assert result["base_url"] == "http://localhost:3000"
        assert result["token"] == "bearer-token-123"

    def test_selected_item_paths_empty_list(self, base_params) -> None:
        """测试空 selected_item_paths 列表对应 run_scope=all."""
        params = dict(base_params, selected_item_paths=[])
        result = build_run_postman_job_params(**params)
        assert result["run_scope"] == "all"
        assert result["selected_count"] == 0

    def test_selected_item_paths_none(self, base_params) -> None:
        """测试 None selected_item_paths 对应 run_scope=all."""
        params = dict(base_params, selected_item_paths=None)
        result = build_run_postman_job_params(**params)
        assert result["run_scope"] == "all"
        assert result["selected_count"] == 0

    def test_selected_item_paths_non_empty(self, base_params) -> None:
        """测试非空 selected_item_paths 对应 run_scope=selected."""
        result = build_run_postman_job_params(**base_params)
        assert result["run_scope"] == "selected"
        assert result["selected_count"] == 2

    def test_optional_report_name_none(self, base_params) -> None:
        """测试 None report_name 回退为空字符串."""
        params = dict(base_params, report_name=None)
        result = build_run_postman_job_params(**params)
        assert result["report_name"] == ""

    def test_optional_base_url_none(self, base_params) -> None:
        """测试 None base_url 保持为 None."""
        params = dict(base_params, base_url=None)
        result = build_run_postman_job_params(**params)
        assert result["base_url"] is None

    def test_optional_token_none(self, base_params) -> None:
        """测试 None token 保持为 None."""
        params = dict(base_params, token=None)
        result = build_run_postman_job_params(**params)
        assert result["token"] is None

    def test_judgment_config_provided(self, base_params) -> None:
        """测试包含 judgment_config 时的字段存在性."""
        config = {"threshold": 0.8, "strategy": "strict"}
        params = dict(base_params, judgment_config=config)
        result = build_run_postman_job_params(**params)
        assert "judgment_config" in result
        assert result["judgment_config"] == config

    def test_judgment_config_none_not_in_result(self, base_params) -> None:
        """测试 judgment_config=None 时不包含该键."""
        params = dict(base_params, judgment_config=None)
        result = build_run_postman_job_params(**params)
        assert "judgment_config" not in result

    def test_return_type_is_dict(self, base_params) -> None:
        """测试返回类型为 Dict."""
        result = build_run_postman_job_params(**base_params)
        assert isinstance(result, dict)

    def test_no_judgment_config_keyword_default_none(self, base_params) -> None:
        """测试省略 judgment_config 关键字参数时默认不包含该字段."""
        # 移除可选参数，使用**展开但不包含 judgment_config
        minimal = {k: v for k, v in base_params.items() if k != "judgment_config"}
        result = build_run_postman_job_params(**minimal)
        assert "judgment_config" not in result


class TestBuildAdHocJobParams:
    """构建 Ad-hoc 任务参数测试."""

    @pytest.fixture
    def base_params(self):
        """返回基础参数."""
        return {
            "job_id": "adhoc-001",
            "source_original_file": "ad-hoc-request.json",
            "saved_file": "/tmp/saved/adhoc.json",
            "output_dir": "/tmp/output",
            "report_name": "adhoc-report",
            "base_url": "http://api.example.com",
            "token": "api-token-456",
        }

    def test_all_fields_present(self, base_params) -> None:
        """测试所有字段都存在时的完整结构."""
        result = build_ad_hoc_job_params(**base_params)
        assert result["id"] == "adhoc-001"
        assert result["status"] == "queued"
        assert result["message"] == "任务已入队，等待执行。"
        assert result["total"] == 0
        assert result["completed"] == 0
        assert result["percent"] == 0
        assert result["current_name"] == ""
        assert result["file_name"] == "ad-hoc-request.json"
        assert result["saved_file"] == "/tmp/saved/adhoc.json"
        assert result["output_dir"] == "/tmp/output"
        assert result["report_name"] == "adhoc-report"

    def test_adhoc_flag_true(self, base_params) -> None:
        """测试 adhoc 标志始终为 True."""
        result = build_ad_hoc_job_params(**base_params)
        assert result["adhoc"] is True

    def test_collection_name_default_empty(self, base_params) -> None:
        """测试 collection_name 默认为空字符串."""
        result = build_ad_hoc_job_params(**base_params)
        assert result["collection_name"] == ""

    def test_run_scope_always_all(self, base_params) -> None:
        """测试 ad-hoc 任务 run_scope 始终为 all."""
        result = build_ad_hoc_job_params(**base_params)
        assert result["run_scope"] == "all"

    def test_selected_count_always_zero(self, base_params) -> None:
        """测试 ad-hoc 任务 selected_count 始终为 0."""
        result = build_ad_hoc_job_params(**base_params)
        assert result["selected_count"] == 0

    def test_no_selected_item_paths_field(self, base_params) -> None:
        """测试 ad-hoc 结果中不包含 selected_item_paths."""
        result = build_ad_hoc_job_params(**base_params)
        assert "selected_item_paths" not in result

    def test_judgment_config_provided(self, base_params) -> None:
        """测试包含 judgment_config 时的字段存在性."""
        config = {"mode": "fast", "timeout": 30}
        params = dict(base_params, judgment_config=config)
        result = build_ad_hoc_job_params(**params)
        assert "judgment_config" in result
        assert result["judgment_config"] == config

    def test_judgment_config_none_not_in_result(self, base_params) -> None:
        """测试 judgment_config=None 时不包含该键."""
        params = dict(base_params, judgment_config=None)
        result = build_ad_hoc_job_params(**params)
        assert "judgment_config" not in result

    def test_optional_report_name_none(self, base_params) -> None:
        """测试 None report_name 回退为空字符串."""
        params = dict(base_params, report_name=None)
        result = build_ad_hoc_job_params(**params)
        assert result["report_name"] == ""

    def test_optional_base_url_none(self, base_params) -> None:
        """测试 None base_url 保持为 None."""
        params = dict(base_params, base_url=None)
        result = build_ad_hoc_job_params(**params)
        assert result["base_url"] is None

    def test_optional_token_none(self, base_params) -> None:
        """测试 None token 保持为 None."""
        params = dict(base_params, token=None)
        result = build_ad_hoc_job_params(**params)
        assert result["token"] is None

    def test_differs_from_run_params(self, base_params) -> None:
        """测试 ad-hoc 与 run 参数的关键差异."""
        adhoc_result = build_ad_hoc_job_params(**base_params)
        # ad-hoc 独有的字段
        assert "adhoc" in adhoc_result
        assert "collection_name" in adhoc_result
        # run 有 selected_item_paths 相关字段，adhoc 没有
        assert "selected_item_paths" not in adhoc_result

    def test_return_type_is_dict(self, base_params) -> None:
        """测试返回类型为 Dict."""
        result = build_ad_hoc_job_params(**base_params)
        assert isinstance(result, dict)


class TestBuildSavedJsonPath:
    """构建保存 JSON 路径测试."""

    def test_creates_directory(self, tmp_path: Path) -> None:
        """测试自动创建目录."""
        new_dir = tmp_path / "new" / "nested" / "dir"
        result = build_saved_json_path(new_dir, "job-100")
        assert new_dir.exists()
        assert new_dir.is_dir()

    def test_returns_correct_path(self, tmp_path: Path) -> None:
        """测试返回正确的路径."""
        job_dir = tmp_path / "jobs"
        result = build_saved_json_path(job_dir, "job-200")
        assert result == job_dir / "job-200.json"

    def test_default_suffix_json(self, tmp_path: Path) -> None:
        """测试默认后缀为 .json."""
        result = build_saved_json_path(tmp_path / "d1", "j-1")
        assert str(result).endswith(".json")
        assert result.name == "j-1.json"

    def test_custom_suffix(self, tmp_path: Path) -> None:
        """测试自定义后缀."""
        result = build_saved_json_path(tmp_path / "d2", "j-2", suffix=".yaml")
        assert result.name == "j-2.yaml"

    def test_custom_suffix_dotless(self, tmp_path: Path) -> None:
        """测试不带点号的前缀作为后缀."""
        result = build_saved_json_path(tmp_path / "d3", "j-3", suffix="backup")
        assert result.name == "j-3backup"

    def test_preserves_existing_directory(self, tmp_path: Path) -> None:
        """测试已存在的目录不会被破坏."""
        existing_dir = tmp_path / "existing"
        existing_dir.mkdir()
        # 放一个已有文件防止 dir 被覆盖
        (existing_dir / "readme.md").write_text("hello")
        result = build_saved_json_path(existing_dir, "j-99")
        assert result == existing_dir / "j-99.json"
        assert (existing_dir / "readme.md").exists()

    def test_path_exists_on_disk(self, tmp_path: Path) -> None:
        """测试返回的路径对应的目录存在于磁盘上."""
        target = tmp_path / "disk_test"
        result = build_saved_json_path(target, "j-disk")
        assert target.exists()

    def test_different_job_ids_get_different_paths(self, tmp_path: Path) -> None:
        """测试不同 job_id 生成不同路径."""
        d = tmp_path / "multi"
        r1 = build_saved_json_path(d, "job-a")
        r2 = build_saved_json_path(d, "job-b")
        assert r1 != r2
        assert r1.name == "job-a.json"
        assert r2.name == "job-b.json"
