"""
Postman API 测试使用示例

示例说明：
1. 从APIFox导出Postman格式的接口文件（JSON格式）
2. 使用本模块加载和执行测试
3. 生成详细的测试报告
"""

import os
import sys

# 确保能导入postman_api_tester模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from postman_api_tester import (
    PostmanApiParser,
    PostmanTestReport,
    PostmanTestExecutor,
    run_postman_tests
)


def example_1_simple_run():
    """
    示例1: 最简单的使用方式
    直接运行Postman文件中的所有API测试
    """
    print("\n" + "="*80)
    print("示例1: 最简单的使用方式".center(80))
    print("="*80)
    
    postman_file = "path/to/your/postman_collection.json"
    
    if os.path.exists(postman_file):
        report = run_postman_tests(postman_file)
    else:
        print(f"✗ 文件不存在: {postman_file}")
        print("请先将Postman导出的JSON文件放到指定位置")


def example_2_with_custom_base_url():
    """
    示例2: 使用自定义的基础URL
    当Postman文件中的基础URL需要被替换时使用
    """
    print("\n" + "="*80)
    print("示例2: 使用自定义的基础URL".center(80))
    print("="*80)
    
    postman_file = "path/to/your/postman_collection.json"
    custom_base_url = "https://your-api.example.com"
    output_dir = "./reports"
    
    if os.path.exists(postman_file):
        report = run_postman_tests(postman_file, custom_base_url, output_dir)
        print(f"\n✓ 测试完成，报告已保存到: {output_dir}")
    else:
        print(f"✗ 文件不存在: {postman_file}")


def example_3_parse_and_analyze():
    """
    示例3: 解析Postman文件并分析API结构
    适合只想查看API信息而不执行测试的场景
    """
    print("\n" + "="*80)
    print("示例3: 解析和分析API结构".center(80))
    print("="*80)
    
    postman_file = "path/to/your/postman_collection.json"
    
    if os.path.exists(postman_file):
        # 解析文件
        parser = PostmanApiParser(postman_file)
        print(f"✓ 文件加载成功")
        
        # 提取所有API
        apis = parser.extract_apis()
        print(f"✓ 发现 {len(apis)} 个API接口\n")
        
        # 显示API列表
        print("API 列表:".ljust(80, "-"))
        for idx, api in enumerate(apis, 1):
            print(f"\n{idx}. {api['name']}")
            print(f"   文件夹: {api.get('folder', '/')}")
            print(f"   方法: {api['method']}")
            print(f"   URL: {api['full_url']}")
            print(f"   请求头数: {len(api.get('headers', {}))}")
            print(f"   请求体: {'有' if api.get('body') else '无'}")
            print(f"   查询参数: {'有' if api.get('params') else '无'}")
            if api.get('description'):
                print(f"   描述: {api['description']}")
    else:
        print(f"✗ 文件不存在: {postman_file}")


def example_4_custom_execution():
    """
    示例4: 自定义执行流程
    对某些API进行特殊处理或过滤
    """
    print("\n" + "="*80)
    print("示例4: 自定义执行流程".center(80))
    print("="*80)
    
    postman_file = "path/to/your/postman_collection.json"
    
    if os.path.exists(postman_file):
        # 解析文件
        parser = PostmanApiParser(postman_file)
        apis = parser.extract_apis()
        
        print(f"✓ 文件加载成功，发现 {len(apis)} 个API接口\n")
        
        # 创建报告
        report = PostmanTestReport()
        
        # 过滤并执行特定的API（例如：只执行GET请求）
        get_apis = [api for api in apis if api['method'] == 'GET']
        print(f"筛选出 {len(get_apis)} 个GET请求\n")
        
        print("开始执行测试...")
        for api in get_apis:
            print(f"  测试: {api['name']} ...", end='')
            
            executor = PostmanTestExecutor(api)
            executor.start()
            result = executor.execute_test()
            report.add_result(result)
            
            status_symbol = "✓" if result['status'] == 'PASSED' else "✗"
            print(f" {status_symbol} {result['status']}")
        
        # 输出报告
        report.print_console_report()
        
        # 保存HTML报告
        report_file = os.path.join("./reports", "custom_test_report.html")
        os.makedirs(os.path.dirname(report_file), exist_ok=True)
        report.generate_html_report(report_file)
        print(f"✓ 报告已保存: {report_file}")
    else:
        print(f"✗ 文件不存在: {postman_file}")


def example_5_multiple_environments():
    """
    示例5: 针对多个环境进行测试
    如：开发环境、测试环境、预发布环境
    """
    print("\n" + "="*80)
    print("示例5: 针对多个环境进行测试".center(80))
    print("="*80)
    
    postman_file = "path/to/your/postman_collection.json"
    environments = {
        'dev': 'https://dev-api.example.com',
        'test': 'https://test-api.example.com',
        'staging': 'https://staging-api.example.com',
        'prod': 'https://api.example.com'
    }
    
    if os.path.exists(postman_file):
        for env_name, base_url in environments.items():
            print(f"\n开始测试 {env_name} 环境 ({base_url})...")
            output_dir = f"./reports/{env_name}"
            
            report = run_postman_tests(postman_file, base_url, output_dir)
            summary = report.generate_summary()
            
            print(f"  ✓ 测试完成 - 通过: {summary['passed']}/{summary['total']}")
    else:
        print(f"✗ 文件不存在: {postman_file}")


def example_6_filter_by_folder():
    """
    示例6: 按文件夹分类测试
    只测试特定文件夹下的API
    """
    print("\n" + "="*80)
    print("示例6: 按文件夹分类测试".center(80))
    print("="*80)
    
    postman_file = "path/to/your/postman_collection.json"
    target_folder = "Users"  # 只测试这个文件夹下的API
    
    if os.path.exists(postman_file):
        # 解析文件
        parser = PostmanApiParser(postman_file)
        apis = parser.extract_apis()
        
        # 按文件夹过滤
        filtered_apis = [api for api in apis if api.get('folder') == target_folder]
        
        print(f"✓ 文件加载成功")
        print(f"  总API数: {len(apis)}")
        print(f"  {target_folder}文件夹API数: {len(filtered_apis)}\n")
        
        if not filtered_apis:
            print(f"✗ 未找到名为 '{target_folder}' 的文件夹")
            print(f"  可用文件夹: {set([api.get('folder') for api in apis])}")
            return
        
        # 创建报告并执行测试
        report = PostmanTestReport()
        
        print(f"开始测试 {target_folder} 文件夹下的API...")
        for api in filtered_apis:
            print(f"  {api['method']:6} {api['name']:30} ...", end='')
            
            executor = PostmanTestExecutor(api)
            executor.start()
            result = executor.execute_test()
            report.add_result(result)
            
            status_symbol = "✓" if result['status'] == 'PASSED' else "✗"
            print(f" {status_symbol}")
        
        # 输出报告
        report.print_console_report()
    else:
        print(f"✗ 文件不存在: {postman_file}")


def show_usage():
    """显示使用说明"""
    print("\n" + "="*80)
    print("Postman API 测试工具 - 使用说明".center(80))
    print("="*80)
    
    print("""
1. 从APIFox导出接口集合为Postman格式（JSON文件）

2. 选择一种使用方式：

   方式A - 命令行执行（最简单）
   -------
   python postman_api_tester/postman_api_tester.py <postman_json_file> [base_url] [output_dir]
   
   示例:
   python postman_api_tester/postman_api_tester.py ./api.json
   python postman_api_tester/postman_api_tester.py ./api.json https://api.example.com ./reports
   

   方式B - Python代码调用
   -------
   from postman_api_tester import run_postman_tests
   
   report = run_postman_tests('path/to/api.json')
   # 或指定基础URL
   report = run_postman_tests('path/to/api.json', base_url='https://api.example.com')


   方式C - 进阶用法（自定义执行）
   -------
   from postman_api_tester import PostmanApiParser, PostmanTestExecutor, PostmanTestReport
   
   # 解析文件
   parser = PostmanApiParser('path/to/api.json')
   apis = parser.extract_apis()
   
   # 创建报告
   report = PostmanTestReport()
   
   # 执行测试
   for api in apis:
       executor = PostmanTestExecutor(api)
       executor.start()
       result = executor.execute_test()
       report.add_result(result)
   
   # 生成报告
   report.print_console_report()
   report.generate_html_report('report.html')


3. 查看测试结果

   - 控制台输出：立即显示测试总结
   - HTML报告：保存在 reports/ 目录，可用浏览器打开查看详细结果


4. 高级功能

   - 多环境测试：针对不同环境（dev、test、prod）分别测试
   - API过滤：按文件夹、方法、状态等条件过滤API
   - 自定义验证：添加额外的响应验证逻辑
   - 集成持续集成：集成到CI/CD流程中


更多示例请查看本文件
""")
    print("="*80 + "\n")


if __name__ == '__main__':
    
    print("""
╔════════════════════════════════════════════════════════════════════════════╗
║                  Postman API 测试工具 - 示例程序                             ║
║                                                                            ║
║  本程序演示如何使用 postman_api_tester 模块进行接口测试                      ║
╚════════════════════════════════════════════════════════════════════════════╝
    """)
    
    show_usage()
    
    # 取消以下任何一行来运行对应的示例
    # example_1_simple_run()
    # example_2_with_custom_base_url()
    # example_3_parse_and_analyze()
    # example_4_custom_execution()
    # example_5_multiple_environments()
    # example_6_filter_by_folder()
