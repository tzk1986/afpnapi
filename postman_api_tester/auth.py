from typing import Dict, List, Optional

import requests

from postman_api_tester.runtime_utils import normalize_url_and_params


def get_auth_token(apis: List[Dict], base_url: str) -> Optional[str]:
    """
    从API列表中获取认证token

    :param apis: API配置列表
    :param base_url: 基础URL
    :return: 认证token，如果获取失败则返回None
    """
    for login_api in apis:
        if not login_api.get('name', '').lower().find('login') >= 0 and not login_api.get('url', '').lower().find('login') >= 0:
            continue
        raw_url = login_api.get('full_url', '') or (base_url.rstrip('/') + '/' + login_api.get('url', '').lstrip('/'))
        method = login_api.get('method', 'POST').lower()
        headers = login_api.get('headers', {})
        body = login_api.get('body')
        params = login_api.get('params', {})
        url, params = normalize_url_and_params(raw_url, params)
        print(f"  尝试登录: {url}")
        try:
            if method == 'post':
                response = requests.post(url, json=body, params=params, headers=headers, timeout=30)
            else:
                response = requests.get(url, params=params, headers=headers, timeout=30)
            if response.status_code == 200:
                try:
                    response_data = response.json()
                    token = None
                    token_fields = ['token', 'access_token', 'accessToken', 'auth_token', 'authorization']

                    if isinstance(response_data, dict):
                        for field in token_fields:
                            if field in response_data:
                                token = response_data[field]
                                break

                        if not token:
                            data = response_data.get('data', {})
                            if isinstance(data, dict):
                                for field in token_fields:
                                    if field in data:
                                        token = data[field]
                                        break

                    if token:
                        print(f"  ✓ 成功获取token: {token[:20]}...")
                        return token
                    else:
                        print("  ✗ 登录成功但未找到token字段")
                        return None

                except Exception as e:
                    print(f"  ✗ 解析登录响应失败: {e}")
                    return None
            else:
                print(f"  ✗ 登录失败，状态码: {response.status_code}")
                return None

        except Exception as e:
            print(f"  ✗ 执行登录请求失败: {e}")
            return None
