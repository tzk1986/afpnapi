"""HTTP 会话与超时策略模块。

开发导读:
- 提供共享 Session 的创建/关闭封装，减少重复连接开销。
- 统一超时配置读取与超时参数规范化逻辑。
"""

from typing import Any, Optional, Protocol, Tuple, cast


RequestTimeout = Tuple[int, int]


class SessionLike(Protocol):
    def get(self, url: str, **kwargs: Any) -> Any:
        ...

    def post(self, url: str, **kwargs: Any) -> Any:
        ...

    def close(self) -> None:
        ...


def create_shared_session() -> SessionLike:
    import requests as _requests_mod
    return cast(SessionLike, _requests_mod.Session())


def close_session(session: Optional[SessionLike]) -> None:
    """关闭共享 Session，失败时记录警告但不中断主流程。"""
    if session is None:
        return
    try:
        session.close()
    except OSError as exc:
        import logging
        logging.getLogger(__name__).warning("关闭 session 时发生 OSError: %s", exc)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("关闭 session 时发生未预期异常: %s", exc)


def resolve_request_timeout(default: RequestTimeout = (10, 30)) -> RequestTimeout:
    """读取配置中的连接与读取超时，异常时回退默认值。"""
    try:
        from postman_api_tester import config as _cfg
        connect_timeout = int(getattr(_cfg, 'REQUEST_CONNECT_TIMEOUT', default[0]))
        read_timeout = int(getattr(_cfg, 'REQUEST_READ_TIMEOUT', default[1]))
        return (connect_timeout, read_timeout)
    except (ValueError, TypeError, AttributeError) as exc:
        import logging
        logging.getLogger(__name__).warning("读取超时配置失败，回退默认值 %s: %s", default, exc)
        return default
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("读取超时配置时发生未预期异常，回退默认值 %s: %s", default, exc)
        return default


def normalize_timeout(timeout: Optional[RequestTimeout], default: RequestTimeout = (10, 30)) -> RequestTimeout:
    """Normalize timeout tuple and fallback to default when invalid."""
    if not timeout:
        return default
    try:
        connect_timeout = int(timeout[0])
        read_timeout = int(timeout[1])
    except (IndexError, ValueError, TypeError):
        return default
    if connect_timeout <= 0 or read_timeout <= 0:
        return default
    return connect_timeout, read_timeout
