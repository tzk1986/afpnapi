# Postman API 测试工具

这是一个基于 Seldom 框架的 Postman 接口测试工具，用于读取从 APIFox/Postman 导出的接口文件，动态生成并执行测试用例，最后生成详细的测试报告。

## 功能特性

✅ **Postman文件解析** - 支持读取和解析标准的 Postman JSON 导出文件
✅ **动态测试生成** - 自动从 Postman 文件生成可执行的测试用例
✅ **多种HTTP方法** - 支持 GET、POST、PUT、DELETE、PATCH 等所有常用HTTP方法
✅ **请求数据处理** - 自动处理 JSON、FormData、URLEncoded 等不同类型的请求体
✅ **灵活的验证** - 支持响应状态码验证和自定义验证规则
✅ **详细报告生成** - 提供 HTML 格式的精美测试报告
✅ **多环境支持** - 支持针对不同环境（指定baseUrl）进行测试
✅ **API过滤** - 支持按文件夹、方法等条件过滤待测API
✅ **易于集成** - 可轻松集成到 CI/CD 流程中

## 文件说明

```
postman_api_tester.py              # 核心模块，包含所有功能类
postman_api_tester_examples.py     # 使用示例代码
POSTMAN_API_TESTER_README.md       # 本说明文档
```

## 核心组件

### 1. PostmanApiParser（Postman文件解析器）

负责读取和解析 Postman JSON 文件，提取 API 接口信息。

**主要功能：**
- 加载 Postman JSON 文件
- 提取基础 URL
- 递归解析文件夹和请求
- 提取 HTTP 方法、URL、请求头、请求体、查询参数等

**主要方法：**
```python
parser = PostmanApiParser("path/to/api.json")
apis = parser.extract_apis()  # 获取所有API列表
base_url = parser.extract_base_url()  # 获取基础URL
```

### 2. PostmanTestExecutor（测试执行器）

继承自 Seldom 的 TestCase，负责执行单个 API 的测试。

**主要功能：**
- 创建 HTTP 会话
- 发送 API 请求
- 验证响应状态码
- 收集测试结果

**主要方法：**
```python
executor = PostmanTestExecutor(api_config)
executor.start()  # 初始化会话
result = executor.execute_test()  # 执行测试
```

### 3. PostmanTestReport（报告生成器）

负责收集测试结果并生成报告。

**主要功能：**
- 存储测试结果
- 生成测试摘要（总数、通过数、失败数等）
- 生成 HTML 格式报告
- 输出控制台报告

**主要方法：**
```python
report = PostmanTestReport()
report.add_result(result)  # 添加单个结果
report.add_results(results)  # 添加多个结果
summary = report.generate_summary()  # 生成摘要
report.generate_html_report("report.html")  # 生成HTML报告
report.print_console_report()  # 打印控制台报告
```

### 4. run_postman_tests（便捷函数）

高级接口函数，一键执行完整的测试流程。

```python
report = run_postman_tests(
    postman_file="path/to/api.json",
    base_url="https://api.example.com",  # 可选，覆盖文件中的baseUrl
    output_dir="./reports"  # 可选，报告输出目录
)
```

## 快速开始

### 方式1: 命令行执行（最简单）

```bash
# 基本用法
python postman_api_tester.py path/to/postman_collection.json

# 指定基础URL
python postman_api_tester.py path/to/postman_collection.json https://api.example.com

# 指定报告输出目录
python postman_api_tester.py path/to/postman_collection.json https://api.example.com ./my_reports
```

### 方式2: Python代码调用

```python
from postman_api_tester import run_postman_tests

# 执行测试
report = run_postman_tests(
    postman_file="api_collection.json",
    base_url="https://api.example.com",
    output_dir="./reports"
)

# 查看测试摘要
summary = report.generate_summary()
print(f"通过: {summary['passed']}/{summary['total']}")
```

### 方式3: 进阶用法（自定义执行）

```python
from postman_api_tester import (
    PostmanApiParser,
    PostmanTestExecutor,
    PostmanTestReport
)

# 1. 解析Postman文件
parser = PostmanApiParser("api_collection.json")
apis = parser.extract_apis()
print(f"发现 {len(apis)} 个API")

# 2. 创建测试报告
report = PostmanTestReport()

# 3. 过滤API（例如：只测试POST请求）
post_apis = [api for api in apis if api['method'] == 'POST']

# 4. 执行测试
for api in post_apis:
    executor = PostmanTestExecutor(api)
    executor.start()
    result = executor.execute_test()
    report.add_result(result)

# 5. 生成报告
report.print_console_report()
report.generate_html_report("./reports/custom_report.html")
```

## 使用示例

### 示例1: 解析和分析API结构

```python
from postman_api_tester import PostmanApiParser

parser = PostmanApiParser("api.json")
apis = parser.extract_apis()

for api in apis:
    print(f"名称: {api['name']}")
    print(f"方法: {api['method']}")
    print(f"URL: {api['full_url']}")
    print(f"请求头: {api['headers']}")
    print(f"请求体: {api['body']}")
    print("-" * 50)
```

### 示例2: 按文件夹过滤并测试

```python
from postman_api_tester import (
    PostmanApiParser, 
    PostmanTestExecutor, 
    PostmanTestReport
)

parser = PostmanApiParser("api.json")
apis = parser.extract_apis()

# 只测试"用户管理"文件夹下的API
user_apis = [api for api in apis if api.get('folder') == '用户管理']

report = PostmanTestReport()
for api in user_apis:
    executor = PostmanTestExecutor(api)
    executor.start()
    result = executor.execute_test()
    report.add_result(result)

report.print_console_report()
```

### 示例3: 多环境测试

```python
from postman_api_tester import run_postman_tests

environments = {
    'dev': 'https://dev.example.com',
    'test': 'https://test.example.com',
    'prod': 'https://api.example.com'
}

for env_name, url in environments.items():
    print(f"\n测试 {env_name} 环境...")
    report = run_postman_tests(
        "api.json",
        base_url=url,
        output_dir=f"./reports/{env_name}"
    )
```

### 示例4: 自定义验证逻辑

```python
from postman_api_tester import PostmanApiParser, PostmanTestExecutor

parser = PostmanApiParser("api.json")
apis = parser.extract_apis()

for api in apis:
    executor = PostmanTestExecutor(api)
    executor.start()
    
    # 执行测试
    response = executor.s.request(
        api['method'].lower(),
        api['full_url'],
        json=api.get('body'),
        headers=api.get('headers')
    )
    
    # 自定义验证
    result = {
        'name': api['name'],
        'method': api['method'],
        'url': api['full_url'],
        'status': 'PASSED' if response.status_code == 200 else 'FAILED',
        'status_code': response.status_code,
        'message': f'响应时间: {response.elapsed.total_seconds()}s'
    }
    
    print(result)
```

## Postman导出格式说明

确保从APIFox/Postman导出的JSON文件包含以下结构：

```json
{
  "info": {
    "name": "API Collection",
    "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
  },
  "variable": [
    { "key": "baseUrl", "value": "https://api.example.com" }
  ],
  "item": [
    {
      "name": "API Name",
      "request": {
        "method": "GET/POST/PUT/DELETE",
        "url": "path/to/endpoint",
        "header": [
          { "key": "Content-Type", "value": "application/json" }
        ],
        "body": {
          "mode": "raw/formdata",
          "raw": "{...}"
        }
      }
    }
  ]
}
```

## 测试结果输出

### 控制台输出

```
================================================================================
                          Postman API 测试报告
================================================================================

总计: 50 | 通过: 48 | 失败: 2 | 错误: 0
成功率: 96.00% | 耗时: 12.34s
开始时间: 2024-01-15 10:30:45 | 结束时间: 2024-01-15 10:30:57

--------------------------------------------------------------------------------
[✓] Get User                          | GET    | PASSED  | 200
