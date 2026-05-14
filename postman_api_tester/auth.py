"""认证辅助模块。

开发导读:
- 负责在集合接口中识别登录候选接口并提取 token。
- 提供自动登录探测与 token 注入的公共能力。
"""

import logging
from typing import Any, Dict, Optional, Sequence, TypedDict

import requests

from postman_api_tester.runtime_utils import normalize_url_and_params
from postman_api_tester.session import RequestTimeout, SessionLike, normalize_timeout

logger = logging.getLogger(__name__)


class ApiLoginCandidate(TypedDict, total=False):
    name: str
    url: str
    full_url: str
    method: str
    headers: Dict[str, Any]
    body: Any
    params: Dict[str, Any]


def _is_login_candidate(api: ApiLoginCandidate) -> bool:
    name = str(api.get("name", "")).lower()
    url = str(api.get("url", "")).lower()
    return ("login" in name) or ("login" in url)


def _extract_token_from_payload(response_data: Any) -> Optional[str]:
    token_fields = ["token", "access_token", "accessToken", "auth_token", "authorization"]
    if not isinstance(response_data, dict):
        return None

    for field in token_fields:
        if field in response_data:
            return response_data.get(field)

    data = response_data.get("data", {})
    if isinstance(data, dict):
        for field in token_fields:
            if field in data:
                return data.get(field)

    return None


def get_auth_token(
    apis: Sequence[ApiLoginCandidate],
    base_url: str,
    *,
    session: Optional[SessionLike] = None,
    request_timeout: Optional[RequestTimeout] = None,
) -> Optional[str]:
    """
    从API列表中获取认证token

    :param apis: API配置列表
    :param base_url: 基础URL
    :return: 认证token，如果获取失败则返回None
    """
    timeout = normalize_timeout(request_timeout, default=(10, 30))
    timeout_value: Any
    timeout_value = timeout
    local_session = session or requests.Session()
    owns_session = session is None

    try:
        for login_api in apis:
            if not _is_login_candidate(login_api):
                continue

            raw_url = login_api.get('full_url', '') or (base_url.rstrip('/') + '/' + login_api.get('url', '').lstrip('/'))
            method = str(login_api.get('method', 'POST')).lower()
            headers = login_api.get('headers', {})
            body = login_api.get('body')
            params = login_api.get('params', {})
            url, params = normalize_url_and_params(raw_url, params)

            logger.info("尝试登录获取 token: %s", url)
            try:
                if method == 'post':
                    response = local_session.post(url, json=body, params=params, headers=headers, timeout=timeout_value)
                else:
                    response = local_session.get(url, params=params, headers=headers, timeout=timeout_value)

                if response.status_code != 200:
                    logger.warning("登录请求失败，状态码: %s, url=%s", response.status_code, url)
                    continue

                try:
                    response_data = response.json()
                except Exception as exc:
                    logger.warning("解析登录响应失败: %s, url=%s", exc, url)
                    continue

                token = _extract_token_from_payload(response_data)
                if token:
                    token_text = str(token)
                    logger.info("成功获取 token: %s...", token_text[:20])
                    return token_text

                logger.warning("登录成功但未找到 token 字段, url=%s", url)
            except Exception as exc:
                logger.warning("执行登录请求失败: %s, url=%s", exc, url)

    finally:
        if owns_session:
            try:
                local_session.close()
            except Exception:
                pass

    return None
