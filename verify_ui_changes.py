#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
UI 优化冒烟验证脚本
验证以下功能：
1. /api/report-results 接口返回 exclusion_key
2. /api/manual-cases 接口返回新字段（status_code、message、err_code）
3. 确保前端代码中包含新按钮样式和函数
"""

import requests
import json
import os
import sys
import urllib.parse

BASE_URL = "http://127.0.0.1:5000"


def get_report_name():
    """从 /api/reports 动态获取一个可用报告名（通常带 .html 后缀）"""
    print("\n0️⃣  获取报告名...")
    url = f"{BASE_URL}/api/reports"
    try:
        resp = requests.get(url, timeout=5)
        if resp.status_code != 200:
            print(f"   ❌ /api/reports 状态码: {resp.status_code}")
            return None
        data = resp.json()
        if not isinstance(data, list) or not data:
            print("   ❌ 报告列表为空")
            return None

        report_name = str(data[0].get("report_name") or "").strip()
        if not report_name:
            print("   ❌ report_name 为空")
            return None

        print(f"   ✅ 使用报告: {report_name}")
        return report_name
    except Exception as e:
        print(f"   ❌ 获取报告名失败: {e}")
        return None


def check_report_results_api(report_name):
    """检查报告结果 API 是否正确返回 exclusion_key"""
    print("\n1️⃣  检查 /api/report-results 接口...")
    encoded_name = urllib.parse.quote(report_name, safe="")
    url = f"{BASE_URL}/api/report-results/{encoded_name}?page=1&page_size=3&include_excluded=true"
    try:
        resp = requests.get(url, timeout=5)
        if resp.status_code != 200:
            print(f"   ❌ 状态码: {resp.status_code}")
            return False
        data = resp.json()
        items = data.get("items", [])
        if not items:
            print(f"   ⚠️  无数据")
            return True
        
        # 检查第一条记录
        first_item = items[0]
        has_exclusion_key = "exclusion_key" in first_item
        has_excluded = "excluded" in first_item
        
        if has_exclusion_key and has_excluded:
            print(f"   ✅ 接口正常")
            print(f"      - 返回条数: {len(items)}")
            print(f"      - exclusion_key 存在: {has_exclusion_key}")
            print(f"      - excluded 字段存在: {has_excluded}")
            return True
        else:
            print(f"   ❌ 缺少关键字段")
            print(f"      - exclusion_key: {has_exclusion_key}")
            print(f"      - excluded: {has_excluded}")
            return False
    except Exception as e:
        print(f"   ❌ 请求失败: {e}")
        return False

def check_manual_cases_api(report_name):
    """检查人工用例 API 是否返回新字段"""
    print("\n2️⃣  检查 /api/manual-cases 接口...")
    encoded_name = urllib.parse.quote(report_name, safe="")
    url = f"{BASE_URL}/api/manual-cases/{encoded_name}"
    try:
        resp = requests.get(url, timeout=5)
        if resp.status_code != 200:
            print(f"   ❌ 状态码: {resp.status_code}")
            return False
        data = resp.json()
        cases = data.get("manual_cases", [])
        
        if not cases:
            print(f"   ⚠️  无人工用例数据")
            return True
        
        # 检查第一条用例
        first_case = cases[0]
        required_fields = ["status_code", "message", "err_code", "exclusion_key", "excluded"]
        missing_fields = [f for f in required_fields if f not in first_case]
        
        if not missing_fields:
            print(f"   ✅ 接口正常")
            print(f"      - 返回用例数: {len(cases)}")
            print(f"      - 包含字段: {', '.join(required_fields)}")
            print(f"      - 第一条用例状态码: {first_case.get('status_code')}")
            return True
        else:
            print(f"   ❌ 缺少字段: {', '.join(missing_fields)}")
            return False
    except Exception as e:
        print(f"   ❌ 请求失败: {e}")
        return False

def check_html_template():
    """检查前端 HTML 模板中是否包含新的样式和函数"""
    print("\n3️⃣  检查前端模板...")
    template_path = "d:\\tangzk\\py\\seldom-api-testing\\templates\\report_view.html"
    
    if not os.path.exists(template_path):
        print(f"   ❌ 模板文件不存在: {template_path}")
        return False
    
    try:
        with open(template_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        checks = {
            ".btn-compact": "新按钮样式类",
            "td.td-op": "操作列容器样式",
            "openManualCaseDetail": "打开人工用例详情函数",
            "toggleCurrentManualCaseExclusion": "排除人工用例函数",
            "renderManualCaseDetailPanels": "渲染人工用例详情函数",
            "btn-compact btn-exclude": "排除按钮样式组合",
            "'排'": "单字排除按钮标文本",
            "'恢'": "单字恢复按钮标文本",
        }
        
        missing = []
        found = []
        for check_str, desc in checks.items():
            if check_str in content:
                found.append(desc)
            else:
                missing.append(desc)
        
        if missing:
            print(f"   ⚠️  缺少以下代码:")
            for m in missing:
                print(f"      - {m}")
        
        print(f"   ✅ 找到 {len(found)} 个关键代码")
        for f in found:
            print(f"      - {f}")
        
        return len(missing) == 0
    except Exception as e:
        print(f"   ❌ 检查失败: {e}")
        return False

def check_health_endpoint():
    """检查健康检查端点"""
    print("\n0️⃣  检查 /health 端点...")
    url = f"{BASE_URL}/health"
    try:
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            if "status" in data and data.get("status") == "ok":
                print(f"   ✅ 服务正常")
                return True
        print(f"   ❌ 状态码: {resp.status_code}")
        return False
    except Exception as e:
        print(f"   ❌ 请求失败: {e}")
        return False

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("🚀 UI 优化冒烟验证开始...")
    print("=" * 60)
    
    results = []
    health_ok = check_health_endpoint()
    results.append(("健康检查", health_ok))

    report_name = get_report_name() if health_ok else None
    if report_name:
        results.append(("报告结果 API", check_report_results_api(report_name)))
        results.append(("人工用例 API", check_manual_cases_api(report_name)))
    else:
        print("\n⚠️  跳过报告相关接口检查（未获取到有效报告名）")
        results.append(("报告结果 API", False))
        results.append(("人工用例 API", False))

    results.append(("前端模板", check_html_template()))
    
    print("\n" + "=" * 60)
    print("📊 验证结果汇总:")
    print("=" * 60)
    
    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{name:20} {status}")
    
    all_passed = all(r for _, r in results)
    print("=" * 60)
    if all_passed:
        print("✨ 所有验证通过！")
        sys.exit(0)
    else:
        print("⚠️  部分验证失败，请检查")
        sys.exit(1)
