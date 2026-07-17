"""数据文件加载与验证。

支持 CSV（UTF-8/UTF-8-sig/GBK）和 JSON（数组对象）两种格式。
"""

from __future__ import annotations

import csv
import json
import os
from typing import Dict, List, Tuple


class DataFileError(Exception):
    """数据文件格式或内容错误。"""


def _detect_csv_encoding(file_path: str) -> str:
    """探测 CSV 文件编码，依次尝试 UTF-8-sig / UTF-8 / GBK。"""
    with open(file_path, "rb") as f:
        raw = f.read(4)
    if raw.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    for encoding in ("utf-8", "gbk"):
        try:
            with open(file_path, encoding=encoding) as f:
                f.read(1024)
            return encoding
        except (UnicodeDecodeError, UnicodeError):
            continue
    return "utf-8"


def _load_csv(file_path: str) -> List[Dict[str, str]]:
    """加载 CSV 文件，首行为变量名。"""
    encoding = _detect_csv_encoding(file_path)
    with open(file_path, encoding=encoding, newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise DataFileError(f"CSV 文件为空或无表头: {file_path}")
        rows: List[Dict[str, str]] = []
        for line_num, row in enumerate(reader, start=2):
            cleaned: Dict[str, str] = {}
            for key, value in row.items():
                if key is None:
                    continue
                cleaned[key.strip()] = (value or "").strip()
            rows.append(cleaned)
        return rows


def _load_json(file_path: str) -> List[Dict[str, str]]:
    """加载 JSON 文件，顶层必须为数组，每个元素为对象。"""
    with open(file_path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise DataFileError(f"JSON 数据文件顶层必须为数组: {file_path}")
    rows: List[Dict[str, str]] = []
    for idx, item in enumerate(data):
        if not isinstance(item, dict):
            raise DataFileError(f"JSON 数组第 {idx + 1} 项不是对象: {file_path}")
        rows.append({str(k): str(v) for k, v in item.items()})
    return rows


def validate_data_file(file_path: str, max_rows: int) -> Tuple[List[Dict[str, str]], str]:
    """验证数据文件并返回 (数据行列表, 格式标识)。

    校验项：
    - 文件存在且可读
    - 扩展名为 .csv 或 .json
    - 行数不超过 max_rows
    - CSV 各行变量名一致（DictReader 天然保证）
    """
    if not os.path.isfile(file_path):
        raise DataFileError(f"数据文件不存在: {file_path}")

    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".csv":
        rows = _load_csv(file_path)
        fmt = "csv"
    elif ext == ".json":
        rows = _load_json(file_path)
        fmt = "json"
    else:
        raise DataFileError(f"不支持的数据文件格式（仅支持 .csv / .json）: {file_path}")

    if len(rows) > max_rows:
        raise DataFileError(
            f"数据文件行数 {len(rows)} 超过限制 {max_rows}: {file_path}"
        )
    if not rows:
        raise DataFileError(f"数据文件为空: {file_path}")

    return rows, fmt


def get_data_columns(rows: List[Dict[str, str]]) -> set[str]:
    """从数据行中提取所有变量名列（并集）。"""
    columns: set[str] = set()
    for row in rows:
        columns.update(row.keys())
    return columns
