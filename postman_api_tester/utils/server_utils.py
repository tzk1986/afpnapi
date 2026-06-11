"""报告服务端通用工具函数。"""

import socket
from typing import Optional, SupportsInt


def get_local_ip() -> str:
    """Return LAN IP and fallback to loopback when detection fails."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return str(sock.getsockname()[0])
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


def clamp_page(value: SupportsInt | str | bytes | bytearray | None) -> int:
    if value is None:
        return 1
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return 1


def clamp_page_size(
    value: SupportsInt | str | bytes | bytearray | None,
    default: int = 20,
    min_size: int = 1,
    max_size: int = 100,
) -> int:
    if value is None:
        page_size = default
    else:
        try:
            page_size = int(value)
        except (TypeError, ValueError):
            page_size = default
    return max(min_size, min(page_size, max_size))
