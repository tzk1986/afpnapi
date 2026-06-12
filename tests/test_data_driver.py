"""数据文件加载单元测试."""

import json
import os
import tempfile

import pytest
from postman_api_tester.utils.data_driver import (
    DataFileError,
    get_data_columns,
    validate_data_file,
)


@pytest.fixture
def tmp_dir() -> str:
    with tempfile.TemporaryDirectory() as d:
        yield d


def _write(path: str, content: str, encoding: str = "utf-8") -> None:
    with open(path, "w", encoding=encoding, newline="") as f:
        f.write(content)


class TestValidateCsv:
    """CSV 加载测试."""

    def test_basic_csv(self, tmp_dir: str) -> None:
        path = os.path.join(tmp_dir, "data.csv")
        _write(path, "name,age\nAlice,30\nBob,25\n")
        rows, fmt = validate_data_file(path, 1000)
        assert fmt == "csv"
        assert len(rows) == 2
        assert rows[0] == {"name": "Alice", "age": "30"}

    def test_csv_utf8_bom(self, tmp_dir: str) -> None:
        path = os.path.join(tmp_dir, "bom.csv")
        _write(path, "name,age\nAlice,30\n", encoding="utf-8-sig")
        rows, _ = validate_data_file(path, 1000)
        assert rows[0]["name"] == "Alice"

    def test_csv_max_rows_exceeded(self, tmp_dir: str) -> None:
        path = os.path.join(tmp_dir, "big.csv")
        _write(path, "id\n" + "\n".join(str(i) for i in range(100)))
        with pytest.raises(DataFileError, match="超过限制"):
            validate_data_file(path, 50)

    def test_csv_empty_file(self, tmp_dir: str) -> None:
        path = os.path.join(tmp_dir, "empty.csv")
        _write(path, "")
        with pytest.raises(DataFileError, match="为空"):
            validate_data_file(path, 1000)


class TestValidateJson:
    """JSON 加载测试."""

    def test_basic_json(self, tmp_dir: str) -> None:
        path = os.path.join(tmp_dir, "data.json")
        data = [{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        rows, fmt = validate_data_file(path, 1000)
        assert fmt == "json"
        assert len(rows) == 2
        assert rows[0]["age"] == "30"

    def test_json_not_array(self, tmp_dir: str) -> None:
        path = os.path.join(tmp_dir, "bad.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"key": "value"}, f)
        with pytest.raises(DataFileError, match="数组"):
            validate_data_file(path, 1000)

    def test_json_non_object_item(self, tmp_dir: str) -> None:
        path = os.path.join(tmp_dir, "bad2.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump([1, 2, 3], f)
        with pytest.raises(DataFileError, match="不是对象"):
            validate_data_file(path, 1000)


class TestValidation:
    """通用验证测试."""

    def test_file_not_found(self) -> None:
        with pytest.raises(DataFileError, match="不存在"):
            validate_data_file("/nonexistent/path.csv", 1000)

    def test_unsupported_extension(self, tmp_dir: str) -> None:
        path = os.path.join(tmp_dir, "data.xlsx")
        _write(path, "fake content")
        with pytest.raises(DataFileError, match="不支持"):
            validate_data_file(path, 1000)


class TestGetDataColumns:
    """get_data_columns() 测试."""

    def test_basic(self) -> None:
        rows = [{"a": "1", "b": "2"}, {"a": "3", "c": "4"}]
        assert get_data_columns(rows) == {"a", "b", "c"}

    def test_empty(self) -> None:
        assert get_data_columns([]) == set()
