#!/usr/bin/env python
"""Run execution-chain smoke modules in one command.

This script runs focused smoke modules sequentially and fails fast on first error.
"""

from __future__ import annotations

import subprocess
import sys
from typing import List


SMOKE_MODULES: List[str] = [
    "test_data.smoke_auth_token_fallback_20260511",
    "test_data.smoke_auth_token_missing_field_fallback_20260511",
    "test_data.smoke_assertion_strict_mode_20260511",
    "test_data.smoke_executor_result_shape_20260511",
    "test_data.smoke_sensitive_headers_20260511",
    "test_data.smoke_collection_query_service_20260511",
]


def run_module(module_name: str) -> int:
    print(f"[smoke-bundle] running: {module_name}")
    result = subprocess.run([sys.executable, "-m", module_name], check=False)
    return int(result.returncode)


def main() -> int:
    for module_name in SMOKE_MODULES:
        code = run_module(module_name)
        if code != 0:
            print(f"[smoke-bundle] failed: {module_name} (exit={code})")
            return code
    print("[smoke-bundle] all execution-chain smoke modules passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
