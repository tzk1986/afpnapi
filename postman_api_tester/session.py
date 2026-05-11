from typing import Optional, Tuple


def create_shared_session():
    import requests as _requests_mod
    return _requests_mod.Session()


def close_session(session) -> None:
    if session is None:
        return
    try:
        session.close()
    except Exception:
        pass


def resolve_request_timeout(default: Tuple[int, int] = (10, 30)) -> Tuple[int, int]:
    """读取配置中的连接与读取超时，异常时回退默认值。"""
    try:
        from postman_api_tester import config as _cfg
        connect_timeout = int(getattr(_cfg, 'REQUEST_CONNECT_TIMEOUT', default[0]))
        read_timeout = int(getattr(_cfg, 'REQUEST_READ_TIMEOUT', default[1]))
        return (connect_timeout, read_timeout)
    except Exception:
        return default
