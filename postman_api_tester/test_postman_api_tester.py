"""
Postman API 测试工具 - 功能验证脚本

用于验证postman_api_tester模块的各项功能是否正常工作
"""

import json
import os
import sys
import tempfile

# 确保能导入postman_api_tester模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from postman_api_tester import (
    PostmanApiParser,
    PostmanTestExecutor,
    PostmanTestReport
)


def create_sample_postman_file() -> str:
    """
    创建一个示例的Postman集合文件
    """
    sample_data = {
        "info": {
            "name": "Sample API Collection",
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
        },
        "variable": [
            {
                "key": "baseUrl",
                "value": "https://httpbin.org"
            }
        ],
        "item": [
            {
                "name": "Get Request",
                "request": {
                    "method": "GET",
                    "url": "/get",
                    "header": [
                        {
                            "key": "Accept",
                            "value": "application/json"
                        }
                    ]
                }
            },
            {
                "name": "Post Request",
                "request": {
                    "method": "POST",
                    "url": "/post",
                    "header": [
                        {
                            "key": "Content-Type",
                            "value": "application/json"
                        }
                    ],
                    "body": {
                        "mode": "raw",
                        "raw": "{\"name\": \"test\", \"value\": 123}"
                    }
                }
            },
            {
                "name": "API Folder",
                "item": [
                    {
                        "name": "Nested GET",
                        "request": {
                            "method": "GET",
                            "url": "/headers",
                            "header": [
                                {
                                    "key": "X-Custom-Header",
                                    "value": "test-value"
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }
    
    # 创建临时文件
    fd, path = tempfile.mkstemp(suffix='.json', text=True)
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        json.dump(sample_data, f, ensure_ascii=False, indent=2)
    
    return path


def test_parser_load_file():
    """测试1: 文件加载"""
    print("\n" + "="*80)
    print("测试1: Postman文件加载".ljust(80))
    print("="*80)
    
    try:
        postman_file = create_sample_postman_file()
        parser = PostmanApiParser(postman_file)
        
        print("✓ 文件成功加载")
        print(f"  文件路径: {postman_file}")
        print(f"  JSON结构有效")
        
        # 清理文件
        os.remove(postman_file)
        return True
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        return False


def test_parser_extract_base_url():
    """测试2: 提取基础URL"""
    print("\n" + "="*80)
    print("测试2: 提取基础URL".ljust(80))
    print("="*80)
    
    try:
        postman_file = create_sample_postman_file()
        parser = PostmanApiParser(postman_file)
        base_url = parser.extract_base_url()
        
        print("✓ 基础URL提取成功")
        print(f"  基础URL: {base_url}")
        
        assert base_url == "https://httpbin.org", "URL不匹配"
        
        # 清理文件
        os.remove(postman_file)
        return True
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        return False


def test_parser_extract_apis():
    """测试3: 提取API列表"""
    print("\n" + "="*80)
    print("测试3: 提取API接口列表".ljust(80))
    print("="*80)
    
    try:
        postman_file = create_sample_postman_file()
        parser = PostmanApiParser(postman_file)
        apis = parser.extract_apis()
        
        print(f"✓ 成功提取 {len(apis)} 个API接口")
        
        for idx, api in enumerate(apis, 1):
            print(f"\n  API{idx}: {api['name']}")
            print(f"    方法: {api['method']}")
            print(f"    URL: {api['full_url']}")
            print(f"    文件夹: {api.get('folder', '/')}")
        
        assert len(apis) >= 3, "API数量不正确"
        
        # 清理文件
        os.remove(postman_file)
        return True
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        return False


def test_parser_http_methods():
    """测试4: HTTP方法识别"""
    print("\n" + "="*80)
    print("测试4: HTTP方法识别".ljust(80))
    print("="*80)
    
    try:
        postman_file = create_sample_postman_file()
        parser = PostmanApiParser(postman_file)
        apis = parser.extract_apis()
        
        methods = {}
        for api in apis:
            method = api['method']
            methods[method] = methods.get(method, 0) + 1
        
        print("✓ HTTP方法统计:")
        for method, count in methods.items():
            print(f"  {method}: {count}个")
        
        assert 'GET' in methods, "未找到GET方法"
        assert 'POST' in methods, "未找到POST方法"
        
        # 清理文件
        os.remove(postman_file)
        return True
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        return False


def test_parser_request_body():
    """测试5: 请求体解析"""
    print("\n" + "="*80)
    print("测试5: 请求体解析".ljust(80))
    print("="*80)
    
    try:
        postman_file = create_sample_postman_file()
        parser = PostmanApiParser(postman_file)
        apis = parser.extract_apis()
        
        post_apis = [api for api in apis if api['method'] == 'POST']
        
        if post_apis:
            api = post_apis[0]
            print(f"✓ 找到POST请求: {api['name']}")
            
            if api.get('body'):
                print(f"  请求体: {api['body']}")
                assert isinstance(api['body'], (dict, str)), "请求体格式错误"
            else:
                print("  请求体: 无")
        
        # 清理文件
        os.remove(postman_file)
        return True
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        return False


def test_parser_headers():
    """测试6: 请求头解析"""
    print("\n" + "="*80)
    print("测试6: 请求头解析".ljust(80))
    print("="*80)
    
    try:
        postman_file = create_sample_postman_file()
        parser = PostmanApiParser(postman_file)
        apis = parser.extract_apis()
        
        print("✓ 请求头统计:")
        for api in apis:
            if api.get('headers'):
                print(f"\n  {api['name']}:")
                for key, value in api['headers'].items():
                    print(f"    {key}: {value}")
        
        # 清理文件
        os.remove(postman_file)
        return True
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        return False


def test_report_generation():
    """测试7: 报告生成"""
    print("\n" + "="*80)
    print("测试7: 报告生成".ljust(80))
    print("="*80)
    
    try:
        report = PostmanTestReport()
        
        # 添加示例结果
        results = [
            {
                'name': 'Get Users',
                'method': 'GET',
                'url': 'https://api.example.com/users',
                'status': 'PASSED',
                'message': '响应状态码: 200',
                'status_code': 200,
                'folder': 'Users'
            },
            {
                'name': 'Create User',
                'method': 'POST',
                'url': 'https://api.example.com/users',
                'status': 'FAILED',
                'message': '期望状态码: 201, 实际: 500',
                'status_code': 500,
                'folder': 'Users'
            },
            {
                'name': 'Delete User',
                'method': 'DELETE',
                'url': 'https://api.example.com/users/1',
                'status': 'PASSED',
                'message': '响应状态码: 204',
                'status_code': 204,
                'folder': 'Users'
            }
        ]
        
        report.add_results(results)
        summary = report.generate_summary()
        
        print("✓ 报告生成成功")
        print(f"\n  总计: {summary['total']}")
        print(f"  通过: {summary['passed']}")
        print(f"  失败: {summary['failed']}")
        print(f"  成功率: {summary['success_rate']}")
        
        # 验证生成HTML报告
        temp_dir = tempfile.mkdtemp()
        report_file = os.path.join(temp_dir, "test_report.html")
        report.generate_html_report(report_file)
        
        if os.path.exists(report_file):
            file_size = os.path.getsize(report_file)
            print(f"\n  HTML报告生成成功")
            print(f"  文件: {report_file}")
            print(f"  大小: {file_size} bytes")
            
            # 清理文件
            os.remove(report_file)
            os.rmdir(temp_dir)
        
        return True
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        return False


def test_api_filtering():
    """测试8: API过滤"""
    print("\n" + "="*80)
    print("测试8: API过滤功能".ljust(80))
    print("="*80)
    
    try:
        postman_file = create_sample_postman_file()
        parser = PostmanApiParser(postman_file)
        apis = parser.extract_apis()
        
        # 按方法过滤
        get_apis = [api for api in apis if api['method'] == 'GET']
        post_apis = [api for api in apis if api['method'] == 'POST']
        
        print(f"✓ 过滤结果:")
        print(f"  总计: {len(apis)}")
        print(f"  GET请求: {len(get_apis)}")
        print(f"  POST请求: {len(post_apis)}")
        
        # 按文件夹过滤
        folder_apis = [api for api in apis if api.get('folder')]
        print(f"  有文件夹的API: {len(folder_apis)}")
        
        # 清理文件
        os.remove(postman_file)
        return True
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        return False


def run_all_tests():
    """运行所有测试"""
    print("\n" + "╔"+"="*78+"╗")
    print("║" + "Postman API 测试工具 - 功能验证".center(78) + "║")
    print("╚"+"="*78+"╝")
    
    tests = [
        test_parser_load_file,
        test_parser_extract_base_url,
        test_parser_extract_apis,
        test_parser_http_methods,
        test_parser_request_body,
        test_parser_headers,
        test_report_generation,
        test_api_filtering
    ]
    
    results = []
    for test_func in tests:
        try:
            result = test_func()
            results.append((test_func.__name__, result))
        except Exception as e:
            print(f"\n✗ 测试异常: {e}")
            results.append((test_func.__name__, False))
    
    # 输出测试摘要
    print("\n" + "="*80)
    print("测试摘要".ljust(80))
    print("="*80)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    print(f"\n总计: {total} | 通过: {passed} | 失败: {total - passed}")
    print(f"成功率: {(passed/total*100):.1f}%\n")
    
    for test_name, result in results:
        status = "✓ PASSED" if result else "✗ FAILED"
        print(f"{status:12} | {test_name}")
    
    print("\n" + "="*80)
    
    if passed == total:
        print("✓ 所有测试通过！模块功能正常！".center(80))
    else:
        print(f"✗ 有 {total - passed} 个测试失败，请检查".center(80))
    
    print("="*80 + "\n")
    
    return passed == total


def main():
    """主函数"""
    import sys
    
    success = run_all_tests()
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
