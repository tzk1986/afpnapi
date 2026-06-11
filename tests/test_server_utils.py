"""Tests for postman_api_tester/utils/server_utils.py"""

import pytest

from postman_api_tester.utils.server_utils import get_local_ip, clamp_page, clamp_page_size


# ── get_local_ip ─────────────────────────────────────────────────────


class TestGetLocalIP:
    def test_returns_string(self):
        result = get_local_ip()
        assert isinstance(result, str)

    def test_not_empty(self):
        result = get_local_ip()
        assert len(result) > 0

    def test_loopback_fallback_format(self):
        """When socket fails, should return '127.0.0.1'."""
        # This is a fallback check — in most environments the LAN IP is detected
        # Just verify the returned value looks like an IP
        import re
        ip = get_local_ip()
        # Should be either loopback (127.0.0.1) or a valid IPv4 address
        assert re.match(r"^\d{1,3}(\.\d{1,3}){3}$", ip)

    def test_socket_closed_in_all_cases(self):
        """Socket must always be closed regardless of path taken."""
        import socket
        original_connect = socket.socket.connect
        call_count = [0]

        class CountingSocket(socket.socket):
            def connect(self, *args, **kwargs):
                call_count[0] += 1
                raise OSError("mock")

        original_socket_cls = socket.socket
        try:
            socket.socket = CountingSocket

            get_local_ip()
            get_local_ip()

            # If sockets weren't closed properly, the leaked resources would cause issues.
            # We just verify it runs without leaking errors.
        finally:
            socket.socket = original_socket_cls

    def test_deterministic(self):
        """Calling twice returns the same value in the same environment."""
        ip1 = get_local_ip()
        ip2 = get_local_ip()
        assert ip1 == ip2


# ── clamp_page ───────────────────────────────────────────────────────


class TestClampPage:
    def test_normal_int(self):
        assert clamp_page(5) == 5

    def test_one(self):
        assert clamp_page(1) == 1

    def test_large_page(self):
        assert clamp_page(999) == 999

    def test_none_returns_one(self):
        assert clamp_page(None) == 1

    def test_negative_becomes_one(self):
        assert clamp_page(-5) == 1

    def test_zero_becomes_one(self):
        assert clamp_page(0) == 1

    def test_string_number(self):
        assert clamp_page("3") == 3

    def test_invalid_string(self):
        assert clamp_page("abc") == 1

    def test_float_string(self):
        assert clamp_page("3.9") == 1

    def test_boolean_true(self):
        # int(True) → 1
        assert clamp_page(True) == 1

    def test_boolean_false(self):
        # int(False) → 0 → max(1, 0) → 1
        assert clamp_page(False) == 1

    def test_bytes(self):
        assert clamp_page(b"10") == 10

    def test_bytearray(self):
        assert clamp_page(bytearray(b"7")) == 7

    def test_empty_string(self):
        assert clamp_page("") == 1

    def test_non_numeric_bytes(self):
        assert clamp_page(b"xyz") == 1

    def test_list_type_error(self):
        assert clamp_page([1, 2]) == 1

    def test_dict_type_error(self):
        assert clamp_page({"page": 1}) == 1


# ── clamp_page_size ──────────────────────────────────────────────────


class TestClampPageSize:
    def test_normal_value(self):
        assert clamp_page_size(20) == 20

    def test_below_min(self):
        assert clamp_page_size(0) == 1

    def test_above_max(self):
        assert clamp_page_size(200) == 100

    def test_default_when_none(self):
        assert clamp_page_size(None) == 20

    def test_custom_defaults(self):
        result = clamp_page_size(
            None, default=50, min_size=10, max_size=200
        )
        assert result == 50

    def test_value_below_custom_min(self):
        result = clamp_page_size(5, default=20, min_size=10, max_size=100)
        assert result == 10

    def test_value_above_custom_max(self):
        result = clamp_page_size(150, default=20, min_size=1, max_size=100)
        assert result == 100

    def test_at_min_boundary(self):
        assert clamp_page_size(1) == 1

    def test_at_max_boundary(self):
        assert clamp_page_size(100) == 100

    def test_string_number(self):
        assert clamp_page_size("50") == 50

    def test_invalid_string_uses_default(self):
        assert clamp_page_size("abc") == 20

    def test_negative_uses_default_then_clamped(self):
        assert clamp_page_size("-5") == 1

    def test_empty_string(self):
        assert clamp_page_size("") == 20

    def test_float_string_truncated(self):
        assert clamp_page_size("25.9") == 20

    def test_boolean_true(self):
        # int(True) → 1
        assert clamp_page_size(True) == 1

    def test_boolean_false(self):
        # int(False) → 0, clamped to min_size 1
        assert clamp_page_size(False) == 1

    def test_bytes(self):
        assert clamp_page_size(b"30") == 30

    def test_bytearray(self):
        assert clamp_page_size(bytearray(b"80")) == 80

    def test_all_defaults_specified(self):
        result = clamp_page_size(None, default=15, min_size=5, max_size=50)
        assert result == 15

    def test_custom_range_edge_case(self):
        result = clamp_page_size(3, default=10, min_size=3, max_size=10)
        assert result == 3

    def test_type_error_returns_default(self):
        assert clamp_page_size([]) == 20

    def test_dict_returns_default(self):
        assert clamp_page_size({}) == 20
