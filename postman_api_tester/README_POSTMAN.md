# Postman API 自动化测试工具

[![Python](https://img.shields.io/badge/Python-3.7%2B-blue)](https://www.python.org/)
[![Seldom](https://img.shields.io/badge/Seldom-3.10.0-green)](https://seldom.readthedocs.io/)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

专业的API接口自动化测试工具 - 读取APIFox/Postman导出的接口定义文件，自动生成并执行测试用例，
提供详细的测试报告。

## ✨ 核心特性

- 🎯 **自动化测试** - 读取Postman JSON文件，自动生成和执行测试
- 📊 **详细报告** - 生成时尚的HTML报告和控制台摘要
- 🌍 **多环境支持** - 轻松针对不同环境（dev/test/prod）进行测试
- 🔄 **CI/CD集成** - 无缝集成到GitHub Actions、Jenkins等
- 🔧 **灵活可配** - 支持API过滤、自定义验证、数据驱动
- 📚 **完整文档** - 快速开始、详细文档、丰富示例

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 导出Postman文件

从APIFox/Postman导出接口集合为JSON格式（Postman v2.1）

### 3. 运行测试

```bash
# 基本用法
python postman_api_tester.py api_collection.json

# 指定基础URL
python postman_api_tester.py api_collection.json https://api.example.com

# 指定报告输出目录
python postman_api_tester.py api_collection.json https://api.example.com ./my_reports
```

### 4. 查看报告

- 📊 **HTML报告** - `./reports/postman_report_YYYYMMDD_HHMMSS.html`
- 📝 **控制台输出** - 立即显示测试摘要

## 📚 文档

| 文档 | 说明 |
|------|------|
| [QUICK_START.md](QUICK_START.md) | 🚀 5分钟快速上手指南 |
| [POSTMAN_API_TESTER_README.md](POSTMAN_API_TESTER_README.md) | 📖 完整功能文档 |
| [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md) | 📋 项目总结和文件说明 |

## 💻 代码示例

### 最简单的用法

```python
from postman_api_tester import run_postman_tests

# 执行测试
report = run_postman_tests('api_collection.json')
```

### 自定义执行

```python
from postman_api_tester import PostmanApiParser, PostmanTestExecutor, PostmanTestReport

# 解析文件
parser = PostmanApiParser('api_collection.json')
apis = parser.extract_apis()

# 创建报告
report = PostmanTestReport()

# 按条件过滤并执行
for api in apis:
    if api['method'] == 'GET':
        executor = PostmanTestExecutor(api)
        executor.start()
        result = executor.execute_test()
        report.add_result(result)

# 生成报告
report.print_console_report()
report.generate_html_report('test_report.html')
```

### 多环境测试

```python
environments = {
    'dev': 'https://dev-api.example.com',
    'test': 'https://test-api.example.com',
    'prod': 'https://api.example.com'
}

for env_name, url in environments.items():
    report = run_postman_tests(
        'api_collection.json',
        base_url=url,
        output_dir=f'./reports/{env_name}'
    )
```

## 📁 项目结构

```
.
├── postman_api_tester.py              # ⭐ 核心模块
├── postman_api_tester_examples.py     # 📖 使用示例代码
├── test_postman_api_tester.py         # ✓ 功能验证脚本
├── POSTMAN_API_TESTER_README.md       # 📚 完整文档
├── QUICK_START.md                     # 🚀 快速开始指南
├── PROJECT_SUMMARY.md                 # 📋 项目总结
├── README.md                          # 📄 本文件
├── requirements.txt                   # 依赖配置
├── reports/                           # 📊 测试报告输出目录
└── test_dir/                          # 现有的seldom测试用例
```

## 🔧 核心组件

### PostmanApiParser

解析Postman文件，提取API接口信息

```python
parser = PostmanApiParser('api.json')
apis = parser.extract_apis()
base_url = parser.extract_base_url()
```

### PostmanTestExecutor

执行单个API的测试

```python
executor = PostmanTestExecutor(api_config)
executor.start()
result = executor.execute_test()
```

### PostmanTestReport

生成测试报告

```python
report = PostmanTestReport()
report.add_result(result)
report.print_console_report()
report.generate_html_report('report.html')
```

## 📊 测试报告示例

### 控制台输出

```
================================================================================
                          Postman API 测试报告
================================================================================

总计: 50 | 通过: 48 | 失败: 2 | 错误: 0
成功率: 96.00% | 耗时: 12.34s

[✓] Get Users          | GET    | PASSED  | 200
[✓] Create User        | POST   | PASSED  | 201
[✗] Delete User        | DELETE | FAILED  | 404
[!] Internal Error     | POST   | ERROR   | 500

================================================================================
```

### HTML报告

包含以下内容：
- 📊 测试汇总（通过率、耗时等）
- 📋 详细结果表格
- 🎨 美观的样式设计
- 📱 响应式布局

## 🎯 支持的功能

✅ **HTTP方法** - GET、POST、PUT、DELETE、PATCH
✅ **请求体** - JSON、FormData、URLEncoded
✅ **请求头** - 完整支持
✅ **查询参数** - 完整支持
✅ **响应验证** - 状态码验证
✅ **文件夹** - 递归解析
✅ **变量** - 支持baseUrl等变量
✅ **异常处理** - 完整的错误捕获

## 🧪 功能验证

运行功能验证脚本，确保所有功能正常：

```bash
python test_postman_api_tester.py
```

输出示例：
```
总计: 8 | 通过: 8 | 失败: 0
成功率: 100.0%

✓ PASSED   | test_parser_load_file
✓ PASSED   | test_parser_extract_base_url
✓ PASSED   | test_parser_extract_apis
✓ PASSED   | test_parser_http_methods
✓ PASSED   | test_parser_request_body
✓ PASSED   | test_parser_headers
✓ PASSED   | test_report_generation
✓ PASSED   | test_api_filtering

✓ 所有测试通过！模块功能正常！
```

## 🔄 CI/CD集成

### GitHub Actions

```yaml
name: API Tests
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
        with:
          python-version: 3.10
      
      - name: Install dependencies
        run: pip install -r requirements.txt
      
      - name: Run API Tests
        run: python postman_api_tester.py api.json ${{ env.API_URL }}
      
      - name: Upload report
        if: always()
        uses: actions/upload-artifact@v2
        with:
          name: test-report
          path: reports/
```

### Jenkins

```groovy
pipeline {
    agent any
    stages {
        stage('API Test') {
            steps {
                sh 'pip install -r requirements.txt'
                sh 'python postman_api_tester.py api.json ${API_BASE_URL}'
            }
        }
        stage('Archive Report') {
            steps {
                archiveArtifacts artifacts: 'reports/**'
            }
        }
    }
}
```

## ❓ 常见问题

**Q: 如何处理需要认证的API？**

A: 在Postman文件中配置Authorization请求头，或在代码中添加：
```python
api['headers']['Authorization'] = 'Bearer token_value'
```

**Q: 支持参数依赖吗？**

A: 支持。执行第一个请求获取token，然后传递给后续请求
```python
token = result1['token']
apis[1]['headers']['Authorization'] = f'Bearer {token}'
```

**Q: 如何过滤特定的API？**

A: 支持按方法、文件夹等条件过滤
```python
get_apis = [api for api in apis if api['method'] == 'GET']
```

**Q: 支持性能测试吗？**
