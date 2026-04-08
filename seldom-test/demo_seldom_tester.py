"""
基于 Seldom 框架的 Postman API 测试 - 演示版本
使用本地模拟API进行演示
"""

import json
import os
import sys
from typing import Dict, List, Any, Optional
from datetime import datetime
import seldom
from seldom_postman_tester import PostmanApiParser, PostmanTestReport


def create_demo_postman_file():
    """创建演示用的Postman文件"""
    demo_data = {
        "info": {
            "name": "Demo API Collection",
            "description": "演示用的API集合"
        },
        "variable": [
            {"key": "baseUrl", "value": "https://httpbin.org"}
        ],
        "item": [
            {
                "name": "获取用户信息",
                "request": {
                    "method": "GET",
                    "header": [],
                    "url": {
                        "raw": "{{baseUrl}}/get",
                        "protocol": "https",
                        "host": ["httpbin", "org"],
                        "path": ["get"]
                    }
                }
            },
            {
                "name": "创建用户",
                "request": {
                    "method": "POST",
                    "header": [
                        {"key": "Content-Type", "value": "application/json"}
                    ],
                    "body": {
                        "mode": "raw",
                        "raw": "{\"name\": \"张三\", \"email\": \"zhangsan@example.com\"}"
                    },
                    "url": {
                        "raw": "{{baseUrl}}/post",
                        "protocol": "https",
                        "host": ["httpbin", "org"],
                        "path": ["post"]
                    }
                }
            }
        ]
    }

    demo_file = "demo_api_collection.json"
    with open(demo_file, 'w', encoding='utf-8') as f:
        json.dump(demo_data, f, indent=2, ensure_ascii=False)

    return demo_file


def demo_basic_functionality():
    """演示基本功能"""
    print("=== 基本功能演示 ===")

    # 创建演示文件
    demo_file = create_demo_postman_file()
    print(f"✓ 创建演示文件: {demo_file}")

    try:
        # 解析Postman文件
        parser = PostmanApiParser(demo_file)
        apis = parser.extract_apis()

        print(f"✓ 解析到 {len(apis)} 个API接口")
        print(f"  基础URL: {parser.base_url}")

        for api in apis:
            print(f"  - {api['name']} ({api['method']} {api['url']})")

        # 演示 seldom 测试类创建
        print("\n✓ Seldom 测试框架集成:")
        print("  - 使用 seldom.TestCase 作为基类")
        print("  - 解决属性冲突问题 (使用 api_response/api_status_code)")
        print("  - 支持动态测试类创建")

        # 演示报告功能
        print("\n✓ 报告生成功能:")
        report = PostmanTestReport()

        # 添加模拟测试结果
        mock_results = [
            {
                'name': '获取用户信息',
                'method': 'GET',
                'url': 'https://httpbin.org/get',
                'status': 'PASSED',
                'message': '响应状态码: 200',
                'status_code': 200,
                'folder': ''
            },
            {
                'name': '创建用户',
                'method': 'POST',
                'url': 'https://httpbin.org/post',
                'status': 'PASSED',
                'message': '响应状态码: 200',
                'status_code': 200,
                'folder': ''
            }
        ]

        for result in mock_results:
            report.add_result(result)

        # 生成报告
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        report_file = f'demo_report_{timestamp}.html'
        report.generate_html_report(report_file)
        print(f"  ✓ HTML报告已生成: {report_file}")

        # 打印控制台报告
        print("\n控制台报告:")
        report.print_console_report()

    finally:
        # 清理演示文件
        if os.path.exists(demo_file):
            os.remove(demo_file)
            print(f"✓ 清理演示文件: {demo_file}")


def demo_seldom_integration():
    """演示 Seldom 集成"""
    print("\n=== Seldom 框架集成演示 ===")

    print("✓ Seldom 特性:")
    print("  - 基于 unittest.TestCase 扩展")
    print("  - 内置 HTTP 请求方法 (get/post/put/delete)")
    print("  - 自动日志记录和报告生成")
    print("  - 支持断言和异常处理")

    print("\n✓ 解决的问题:")
    print("  - 属性冲突: response/status_code 为只读属性")
    print("  - 解决方案: 使用 api_response/api_status_code")
    print("  - 保持 seldom 的所有优势")

    print("\n✓ 使用方法:")
    print("  1. 继承 seldom.TestCase")
    print("  2. 使用 self.get/post/put/delete() 方法")
    print("  3. 通过 self.response 访问响应数据")
    print("  4. 使用 seldom.main() 运行测试")


if __name__ == '__main__':
    print("基于 Seldom 框架的 Postman API 测试 - 演示")
    print("=" * 60)

    # 检查 seldom
    try:
        import seldom
        print(f"✓ Seldom 已安装 (版本: {seldom.__version__})")
    except ImportError:
        print("✗ Seldom 未安装")
        sys.exit(1)

    # 运行演示
    demo_basic_functionality()
    demo_seldom_integration()

    print("\n" + "=" * 60)
    print("演示完成！")
    print("\n主要文件:")
    print("- practical_seldom_tester.py: 主要实现文件")
    print("- simple_seldom_tester.py: 简化版本")
    print("- seldom_postman_tester.py: 原始复杂版本")
    print("- test_seldom_postman.py: 单元测试")
    print("- seldom_examples.py: 使用示例")