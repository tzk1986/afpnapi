#!/usr/bin/env python
import requests
import urllib.parse

# 获取报告列表
resp = requests.get('http://127.0.0.1:5000/api/list-reports')
if resp.status_code == 200:
    data = resp.json()
    reports = data.get('reports', [])
    if reports:
        report_name = reports[0].get('name')
        print(f'第一个报告: {report_name}')
        
        # 尝试查询报告结果
        encoded_name = urllib.parse.quote(report_name, safe='')
        test_url = f'http://127.0.0.1:5000/api/report-results/{encoded_name}?page=1&page_size=3'
        print(f'测试 URL: {test_url}')
        resp2 = requests.get(test_url)
        print(f'查询状态码: {resp2.status_code}')
        if resp2.status_code == 200:
            data2 = resp2.json()
            print(f'返回项数: {len(data2.get("items", []))}')
            if data2.get('items'):
                print(f'第一项有 exclusion_key: {"exclusion_key" in data2["items"][0]}')
    else:
        print('无报告')
else:
    print(f'获取报告列表失败: {resp.status_code}')
