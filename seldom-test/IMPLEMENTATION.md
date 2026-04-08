# 方案实现方式

seldom-test 项目的核心设计理念、技术方案和实现细节

## 🎯 项目目标

### 核心需求
1. ✅ 支持 Postman Collection 导入
2. ✅ 集成 Seldom 测试框架
3. ✅ 解决框架属性冲突问题
4. ✅ 完整的测试报告和日志
5. ✅ 支持自定义 Base URL
6. ✅ 动态测试用例生成

### 解决的主要问题

| 问题 | 原因 | 解决方案 |
|------|------|--------|
| 属性冲突 | Seldom 的 response/status_code 是只读的 | 使用 api_response/api_status_code 替代 |
| 动态测试 | 无法在运行时创建测试类 | 使用 `type()` 动态生成类 |
| URL 拼接 | 支持相对 URL | 使用 urllib.parse.urljoin() |
| 报告生成 | 需要美观的报告 | 自定义 HTML 模板 + Seldom 日志 |

---

## 🏗️ 整体架构

### 三层架构

```
┌─────────────────────────────────────────────────────┐
│          测试执行层 (Test Execution)               │
│  ┌─────────────────────────────────────────────┐   │
│  │  run_seldom_postman_tests()                 │   │
│  │  - 入口函数，协调整个测试流程               │   │
│  └─────────────────────────────────────────────┘   │
└────────────────┬────────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────────┐
│          业务逻辑层 (Business Logic)               │
│  ┌─────────────────┐      ┌────────────────────┐  │
│  │ PostmanApiParser│      │ create_api_test_   │  │
│  │                 │      │ class()            │  │
│  │ - 解析 JSON     │      │ - 动态创建类       │  │
│  │ - 提取 API 信息 │      │ - 执行单个测试     │  │
│  └─────────────────┘      └────────────────────┘  │
│         ▲                           ▲              │
└────────┼───────────────────────────┼──────────────┘
         │                           │
┌────────┼───────────────────────────▼──────────────┐
│          基础设施层 (Infrastructure)              │
│  ┌──────────────┐  ┌──────────────────────────┐ │
│  │ Seldom.HTTP  │  │ PostmanTestReport        │ │
│  │ Methods      │  │ - HTML 报告生成          │ │
│  │ - get()      │  │ - 控制台输出             │ │
│  │ - post()     │  │ - 统计数据计算           │ │
│  │ - put()      │  └──────────────────────────┘ │
│  │ - delete()   │                                │
│  └──────────────┘                                │
└──────────────────────────────────────────────────┘
```

---

## 🔑 关键技术方案

### 1. 属性冲突解决方案

**问题描述**:
```python
# ❌ Seldom 的 response/status_code 是只读属性
class MyTest(seldom.TestCase):
    def test(self):
        self.response = self.get(url)  # ❌ AttributeError: can't set attribute
        self.status_code = 200         # ❌ AttributeError: can't set attribute
```

**解决方案**:
```python
# ✅ 使用自定义属性名
class APITestCase(seldom.TestCase):
    def __init__(self, api_config):
        super().__init__()
        self.api_config = api_config
        # 使用不同的属性名
        self.api_response = None
        self.api_status_code = None
    
    def test_api(self):
        # 访问 Seldom 的 self.response（只读）
        resp = self.get(url)
        
        # 保存到自定义属性
        self.api_response = resp
        self.api_status_code = resp.status_code
```

**优势**:
- ✅ 完全避免冲突
- ✅ 保持 Seldom 的所有功能
- ✅ 代码清晰易理解

---

### 2. 动态测试类生成方案

**核心思想**: 使用 Python 的 `type()` 函数动态创建测试类

```python
def create_api_test_class(api_config: Dict):
    """动态创建测试类"""
    
    # 1. 定义测试方法
    def test_api(self):
        # 具体实现...
        resp = self.get(url)
        self.assertEqual(resp.status_code, expected_status)
    
    # 2. 使用 type() 创建新类
    class_name = f"Test{api_config['name'].replace(' ', '')}"
    TestClass = type(
        class_name,                    # 类名
        (seldom.TestCase,),           # 父类
        {
            'api_config': api_config,
            'test_api': test_api
        }
    )
    
    return TestClass
```

**工作流程**:
```
API 配置 dict
   │
   ├─ 创建内部类定义
   │  ├─ 继承 seldom.TestCase
   │  └─ 实现 test_api() 方法
   │
   ├─ 使用 type() 动态生成类
   │  ├─ 设置类名
   │  ├─ 指定父类
   │  └─ 添加属性方法
   │
   └─> 返回测试类
       可以立即实例化和执行
```

**优势**:
- 📦 高度灵活
- 🎯 每个 API 一个独立类
- 🔄 支持动态修改参数

---

### 3. Postman JSON 解析方案

**递归解析策略**:

```python
def _parse_item(self, item: Dict, parent_name: str = ""):
    """递归处理 item（文件夹或请求）"""
    
    # Case 1: 文件夹结构 (item 中有 item 属性但没有 request)
    if 'item' in item and 'request' not in item:
        folder_name = item.get('name', '')
        for sub_item in item['item']:
            # 递归处理子项目
            self._parse_item(sub_item, folder_name)
        return None
    
    # Case 2: 具体请求 (item 中有 request 属性)
    if 'request' in item:
        return self._parse_request(item, parent_name)
    
    return None
```

**支持的 Postman 结构**:
```
Collection
├─ Variables (baseUrl, token, etc.)
└─ Items
   ├─ Folder 1
   │  ├─ Request 1
   │  └─ Request 2
   │
   ├─ Folder 2
   │  └─ Request 3
   │
   └─ Request 4
```

**解析的 API 字段**:
- `name`: 请求名称
- `method`: HTTP 方法 (GET/POST/PUT/DELETE/PATCH)
- `url`: 相对 URL 路径
- `full_url`: 完整 URL (base_url + 相对 URL)
- `headers`: 请求头字典
- `body`: 请求体 (支持 raw/formdata/urlencoded)
- `params`: 查询参数字典
- `expected_status`: 期望响应状态码
- `folder`: 所属文件夹名称
- `description`: 请求描述

---

### 4. URL 拼接方案

**支持的 URL 格式**:

```python
# 格式 1: 相对 URL (推荐)
base_url = "https://api.example.com"
url = "/users"
full_url = urljoin(base_url, url)
# 结果: "https://api.example.com/users"

# 格式 2: 完整 URL (直接使用)
url = "https://api.example.com/users"
full_url = urljoin(base_url, url)
# 结果: "https://api.example.com/users" (不受影响)

# 格式 3: URL 中包含查询参数
url = "/users?page=1&limit=10"
full_url = urljoin(base_url, url)
# 结果: "https://api.example.com/users?page=1&limit=10"

# 格式 4: Postman 字典格式
url_dict = {
    'protocol': 'https',
    'host': ['api', 'example', 'com'],
    'path': ['users', '123'],
    'query': [{'key': 'format', 'value': 'json'}]
}
# 内部转换为: https://api.example.com/users/123?format=json
```

**使用 urllib.parse.urljoin() 的原因**:
- ✅ 正确处理路径拼接
- ✅ 自动处理重复的 `/`
- ✅ 支持完整 URL 覆盖
- ✅ 标准库，无依赖

---

### 5. 报告生成方案

#### HTML 报告流程

```python
# 1. 收集所有测试结果
results = [
    {'name': 'API1', 'status': 'PASSED', ...},
    {'name': 'API2', 'status': 'FAILED', ...}
]

# 2. 计算统计信息
summary = {
    'total': 2,
    'passed': 1,
    'failed': 1,
    'success_rate': '50%',
    'duration': '2.34s'
}

# 3. 生成 HTML
html = f"""
<html>
  <head>
    <style>{css_styles}</style>
  </head>
  <body>
    <div class="summary">{summary}</div>
    <table>{results_table}</table>
  </body>
</html>
"""

# 4. 保存文件
open(output_path, 'w').write(html)
```

#### 控制台输出格式

```
================================================================================
                            Postman API 测试报告                         
================================================================================

总计: 5 | 通过: 5 | 失败: 0 | 错误: 0
成功率: 100.00% | 耗时: 2.34s
开始时间: 2026-04-08 09:50:29 | 结束时间: 2026-04-08 09:50:29

------------------------------------------------------------------------
详细结果:
------------------------------------------------------------------------
[✓] API 名称1                 | GET    | PASSED   | 200
    URL: https://api.example.com/endpoint1
    响应状态码: 200
[✗] API 名称2                 | POST   | FAILED   | 500
    URL: https://api.example.com/endpoint2
    期望状态码: 200, 实际: 500
================================================================================
```

---

## 🔄 完整执行流程

### 时序图

```
用户
  │
  ├─> run_seldom_postman_tests(file, url)
  │   │
  │   ├─> PostmanApiParser(file)
  │   │   │
  │   │   ├─> load_file() ───────> 读取 JSON
  │   │   │
  │   │   ├─> extract_base_url() ──> 提取 baseUrl
  │   │   │
  │   │   └─> extract_apis() ──────> 解析所有 API
  │   │       │
  │   │       ├─> _parse_item() ──> 递归遍历
  │   │       │
  │   │       └─> _parse_request() ​> 解析请求
  │   │           返回: List[api_dict]
  │   │
  │   ├─> for each api in apis:
  │   │   │
  │   │   ├─> create_api_test_class(api)
  │   │   │   │
  │   │   │   ├─> 定义 test_api() 方法
  │   │   │   │
  │   │   │   ├─> type() 生成类
  │   │   │   │
  │   │   │   └─> 返回 TestClass
  │   │   │
  │   │   └─> test_instance.test_api()
  │   │       │
  │   │       ├─> self.get/post/put/delete(url)
  │   │       │   │
  │   │       │   └─> Seldom 发送请求
  │   │       │
  │   │       ├─> 获取响应
  │   │       │
  │   │       ├─> 验证状态码
  │   │       │
  │   │       └─> 返回结果 dict
  │   │
  │   ├─> PostmanTestReport()
  │   │
  │   ├─> report.add_results(results)
  │   │
  │   ├─> report.generate_html_report()
  │   │   └─> HTML 文件
  │   │
  │   └─> report.print_console_report()
  │       └─> 控制台输出
  │
  └─> results 返回用户
```

---

## 🛡️ 错误处理机制

### 多层错误捕获

```python
# 第一层：文件加载错误
try:
    with open(file_path) as f:
        data = json.load(f)
except FileNotFoundError:
    raise FileNotFoundError(f"文件不存在: {file_path}")
except json.JSONDecodeError:
    raise ValueError(f"JSON格式错误: {file_path}")

# 第二层：API 解析错误
try:
    api_dict = self._parse_request(item)
except Exception as e:
    # 记录或跳过有问题的 API
    log_warning(f"解析 API 失败: {e}")

# 第三层：HTTP 请求错误
try:
    response = self.get(url)
except ConnectionError as e:
    return {'status': 'ERROR', 'message': str(e)}
except Timeout as e:
    return {'status': 'ERROR', 'message': f'请求超时: {e}'}

# 第四层：响应验证错误
if response.status_code != expected_status:
    return {'status': 'FAILED', 'message': f'...'}
```

---

## 📊 性能指标

### 测试执行性能

```
场景
  │
  ├─ 小规模 (5-10 个 API)
  │  └─ 耗时: 1-3 秒
  │     吞吐量: 2-5 个 API/秒
  │
  ├─ 中等规模 (50 个 API)
  │  └─ 耗时: 10-30 秒
  │     吞吐量: 2-5 个 API/秒
  │
  └─ 大规模 (100+ 个 API)
     └─ 耗时: > 60 秒
        吞吐量: 2-5 个 API/秒
        
瓶颈：网络延迟 (主要因素)
    └─> 单个请求通常 500ms-2s 不等
```

### 内存占用

```
API 数量   | 内存占用 | 说明
-----------|---------|----------
10         | ~10MB   | 轻量
50         | ~30MB   | 正常
100        | ~60MB   | 可接受
500        | ~200MB  | 较大
1000+      | ~400MB+ | 需要优化
```

---

## 🎓 设计模式使用

### 1. 工厂模式（Factory Pattern）

```python
# create_api_test_class() 就是工厂方法
def create_api_test_class(api_config):
    """工厂方法：根据配置创建测试类"""
    # ... 创建逻辑 ...
    return TestClass
```

### 2. 策略模式（Strategy Pattern）

```python
# 不同的 HTTP 方法实现
if method == 'get':
    strategy = self.get
elif method == 'post':
    strategy = self.post
# 使用策略
strategy(url, **kwargs)
```

### 3. 模板方法模式（Template Method）

```python
# Seldom.TestCase 定义了测试框架
class APITestCase(seldom.TestCase):
    # 实现具体的测试方法
    def test_api(self):
        # ...
```

### 4. 装饰器模式（Decorator）

```python
# Seldom 自动装饰 HTTP 方法
@wrapper  # 日志记录、性能监测等
def get(self, url):
    return requests.get(url)
```

---

## 🔐 安全考虑

### 1. 敏感信息处理

```python
# ❌ 不要在日志中输出敏感信息
log(f"Authorization: {headers['Authorization']}")

# ✅ 应该隐藏敏感信息
if 'Authorization' in headers:
    headers_log = headers.copy()
    headers_log['Authorization'] = '***'
    log(f"Headers: {headers_log}")
```

### 2. URL 验证

```python
# ✅ 验证 URL 格式
if not url.startswith(('http://', 'https://')):
    raise ValueError(f"Invalid URL: {url}")
```

### 3. 文件路径安全

```python
# ✅ 使用绝对路径避免路径遍历
import os.path
safe_path = os.path.abspath(file_path)
```

---

## 📋 扩展指南

### 如何添加新的 HTTP 方法

```python
# 1. 在测试类中添加方法
elif method == 'options':
    response = self.options(url)

# 2. Seldom 已内置支持，直接使用
```

### 如何自定义报告模板

```python
# 编辑 PostmanTestReport.generate_html_report()
# 修改 html_content 变量中的 HTML 模板
# 添加自定义 CSS 和 HTML 结构
```

### 如何集成 CI/CD

```python
# 在脚本末尾添加
if __name__ == '__main__':
    results = run_seldom_postman_tests(...)
    
    # 统计测试结果
    failed = len([r for r in results if r['status'] != 'PASSED'])
    
    # 根据失败数量返回退出码
    sys.exit(failed)
```

---

## 📚 参考资源

- [Seldom 官方文档](https://github.com/SeldomQA/seldom)
- [Postman Collection v2.1 Schema](https://schema.postman.com/collection/json/v2.1.0/)
- [Python unittest 文档](https://docs.python.org/3/library/unittest.html)
- [urllib.parse 文档](https://docs.python.org/3/library/urllib.parse.html)

---

更多信息请查看其他文档：
- [QUICKSTART.md](QUICKSTART.md) - 快速使用指南
- [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) - 项目结构详解
- [README.md](README.md) - 功能说明