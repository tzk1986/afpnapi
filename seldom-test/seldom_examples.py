"""
基于 Seldom 框架的 Postman API 测试 - 使用示例
演示如何使用 seldom 版本的 Postman 测试工具
"""

import os
import sys
from simple_seldom_tester import run_seldom_tests


def example_basic_usage():
    """基本使用示例"""
    print("=== 基本使用示例 ===")

    # 假设 Postman 文件在上级目录
    postman_file = "../sample_api_collection.json"

    if os.path.exists(postman_file):
        results = run_seldom_tests(postman_file)
        print(f"测试完成，结果数量: {len(results)}")
    else:
        print(f"Postman 文件不存在: {postman_file}")


def example_with_custom_base_url():
    """自定义基础URL示例"""
    print("\n=== 自定义基础URL示例 ===")

    postman_file = "../sample_api_collection.json"
    custom_base_url = "https://httpbin.org"

    if os.path.exists(postman_file):
        results = run_seldom_tests(postman_file, custom_base_url)
        print(f"使用自定义URL测试完成，结果数量: {len(results)}")
    else:
        print(f"Postman 文件不存在: {postman_file}")


def example_parse_only():
    """仅解析示例"""
    print("\n=== 仅解析示例 ===")

    from seldom_postman_tester import PostmanApiParser

    postman_file = "../sample_api_collection.json"

    if os.path.exists(postman_file):
        parser = PostmanApiParser(postman_file)
        apis = parser.extract_apis()

        print(f"解析到 {len(apis)} 个API:")
        for api in apis:
            print(f"  - {api['name']} ({api['method']} {api['url']})")
    else:
        print(f"Postman 文件不存在: {postman_file}")


def example_manual_test():
    """手动创建测试示例"""
    print("\n=== 手动创建测试示例 ===")

    from seldom_postman_tester import PostmanAPITest

    # 手动创建API配置
    api_config = {
        'name': '测试API',
        'method': 'GET',
        'url': '/get',
        'full_url': 'https://httpbin.org/get',
        'headers': {},
        'body': None,
        'params': {},
        'expected_status': 200
    }

    # 创建测试实例
    test_instance = PostmanAPITest(api_config)

    print("创建测试实例成功")
    print(f"API名称: {test_instance.api_config['name']}")
    print(f"请求方法: {test_instance.api_config['method']}")
    print(f"完整URL: {test_instance.api_config['full_url']}")


if __name__ == '__main__':
    print("基于 Seldom 框架的 Postman API 测试 - 使用示例")
    print("=" * 60)

    # 检查是否安装了 seldom
    try:
        import seldom
        print("✓ Seldom 已安装")
    except ImportError:
        print("✗ Seldom 未安装，请运行: pip install seldom")
        sys.exit(1)

    # 运行示例
    example_basic_usage()
    example_with_custom_base_url()
    example_parse_only()
    example_manual_test()

    print("\n" + "=" * 60)
    print("所有示例运行完成！")
    print("\n提示:")
    print("- 确保 Postman JSON 文件存在")
    print("- 可以修改 base_url 来测试不同的环境")
    print("- 查看 seldom_postman_report.html 获取详细报告")