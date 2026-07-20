"""
运行时工具模块 - 提供 URL、参数、checkpoint 等工具函数

### 职责划分（async/sync）

**同步优先（SYNC-ONLY）**：
  - normalize_url_and_params() - URL 与参数合并
  - merge_url_with_params() - URL 与参数拼接
  - item_path_text() - 项路径序列化
  - compute_collection_fingerprint() - 集合指纹计算
  - checkpoint_file_path() - checkpoint 路径生成
  - load_checkpoint() - checkpoint 读取
  - save_checkpoint() - checkpoint 保存

**说明**：
  所有导出函数均为**同步阻塞**操作。
  - 磁盘 I/O（checkpoint 读写）采用同步模式，适合小文件场景
  - 如需支持并发大量 checkpoint 操作，建议在上层使用 asyncio.to_thread 或线程池
  - 不提供原生 async 版本，以保持代码简洁与一致性
"""

import hashlib
import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def normalize_url_and_params(raw_url: str, params: Optional[Dict[str, Any]]) -> Tuple[str, Dict[str, Any]]:
    """Normalize a request URL and merge query params without duplicates."""
    url_text = str(raw_url or "").strip()
    split = urlsplit(url_text)

    merged_params: Dict[str, Any] = {}
    for key, value in parse_qsl(split.query, keep_blank_values=True):
        merged_params[str(key)] = value

    if isinstance(params, dict):
        for key, value in params.items():
            merged_params[str(key)] = value

    if split.query:
        clean_url = urlunsplit((split.scheme, split.netloc, split.path, "", split.fragment))
    else:
        clean_url = url_text

    return clean_url, merged_params


def merge_url_with_params(raw_url: str, params: Dict[str, Any]) -> str:
    clean_url, merged_params = normalize_url_and_params(raw_url, params)
    if not merged_params:
        return clean_url
    normalized = {str(key): "" if value is None else str(value) for key, value in merged_params.items()}
    split = urlsplit(clean_url)
    new_query = urlencode(normalized, doseq=False)
    return urlunsplit((split.scheme, split.netloc, split.path, new_query, split.fragment))


def item_path_text(path: Any) -> str:
    if not isinstance(path, list):
        return ""
    if not all(isinstance(index, int) and index >= 0 for index in path):
        return ""
    return ".".join(str(index) for index in path)


def checkpoint_key(path: Any, data_index: int = 0) -> str:
    """生成 checkpoint 复合键。

    非展开接口（data_index=0）使用 ``"0.2.1"`` 格式，与旧 checkpoint 向后兼容。
    展开接口（data_index>0）使用 ``"0.2.1#3"`` 格式。
    """
    base = item_path_text(path)
    if not base:
        return ""
    if data_index <= 0:
        return base
    return f"{base}#{data_index}"


def compute_collection_fingerprint(
    postman_file: str,
    base_url: str,
    selected_item_paths: Optional[List[List[int]]],
    data_file: str = "",
) -> str:
    hasher = hashlib.sha256()
    with open(postman_file, "rb") as file:
        while True:
            chunk = file.read(1024 * 1024)
            if not chunk:
                break
            hasher.update(chunk)
    hasher.update((base_url or "").encode("utf-8"))
    hasher.update(json.dumps(selected_item_paths or [], ensure_ascii=False, sort_keys=True).encode("utf-8"))
    if data_file and os.path.isfile(data_file):
        with open(data_file, "rb") as df:
            while True:
                chunk = df.read(1024 * 1024)
                if not chunk:
                    break
                hasher.update(chunk)
    return hasher.hexdigest()


def checkpoint_file_path(output_dir: str, postman_file: str, fingerprint: str, checkpoint_dir: str = "") -> str:
    if checkpoint_dir:
        base_dir = checkpoint_dir
    else:
        base_dir = os.path.join(output_dir, "checkpoints")
    os.makedirs(base_dir, exist_ok=True)
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", os.path.splitext(os.path.basename(postman_file))[0]).strip("._") or "collection"
    return os.path.join(base_dir, f"{stem}_{fingerprint[:16]}.checkpoint.json")


def load_checkpoint(path: str) -> Optional[Dict[str, Any]]:
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as file:
            data = json.load(file)
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    executed = data.get("executed_item_paths")
    if not isinstance(executed, list):
        return None
    if not all(isinstance(item, str) for item in executed):
        return None
    return data


def save_checkpoint_atomic(path: str, data: Dict[str, Any]) -> None:
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False)
    os.replace(tmp_path, path)
