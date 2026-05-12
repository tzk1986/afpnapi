"""Compatibility layer for request builder utilities.

Real implementation is centralized in postman_api_tester.utils.request_builder.
"""

from postman_api_tester.utils.request_builder import (  # noqa: F401
    build_request_kwargs,
    infer_body_mode_from_stored_body,
    normalize_formdata_rows,
    normalize_graphql_data,
    normalize_urlencoded_rows,
    set_request_body,
    set_request_headers,
    set_request_url,
)

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
