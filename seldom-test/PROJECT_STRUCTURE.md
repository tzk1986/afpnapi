# 项目结构详解

seldom-test 项目的深度结构说明和各部分功能介绍

## 📂 项目总体结构

```
seldom-test/
├── README.md                      # 详细功能说明
├── QUICKSTART.md                  # 快速使用指南（本文件）
├── IMPLEMENTATION.md              # 实现方案详解
├── PROJECT_STRUCTURE.md           # 项目结构说明
├── requirements.txt               # Python 依赖
├── __init__.py                    # 包初始化
│
├── 核心文件
│   ├── practical_seldom_tester.py     # ★ 推荐使用 - 主要实现
│   ├── seldom_postman_tester.py       # 原始版本 - 复杂实现
│   └── simple_seldom_tester.py        # 简化版本 - 手动执行
│
├── 辅助文件
│   ├── demo_seldom_tester.py          # 演示脚本
│   ├── seldom_examples.py             # 使用示例
│   └── test_seldom_postman.py         # 单元测试
│
└── 输出文件
    ├── demo_report_*.html             # 演示报告
    └── reports/                       # 测试报告目录
        ├── seldom_postman_report_*.html
        └── ...
```

## 📋 核心文件详解

### 1. practical_seldom_tester.py（★推荐）

**位置**: 根目录  
**大小**: ~350 行  
**用途**: 主要测试执行文件

**主要类**:

```python
class PostmanApiParser:
    """Postman 接口文件解析器"""
    - load_file()              # 加载 JSON 文件
    - extract_base_url()       # 提取基础 URL
    - extract_apis()           # 提取所有 API
    - _parse_item()            # 递归解析项目
    - _parse_request()         # 解析单个请求
    - _build_url_from_dict()   # 从字典构建 URL

def create_api_test_class(api_config):
    """动态创建 API 测试类"""
    - 继承 seldom.TestCase
    - 实现 test_api() 方法
    - 自动处理 HTTP 请求

def run_seldom_postman_tests(postman_file, base_url, output_dir):
    """主要测试运行函数"""
    - 解析 Postman 文件
    - 创建测试类
    - 执行测试
    - 生成报告
```

**特点**:
- ✅ 简洁高效
- ✅ 支持动态测试类创建
- ✅ 完整的报告生成
- ✅ 生产环境推荐使用

**使用方式**:
```python
from practical_seldom_tester import run_seldom_postman_tests
results = run_seldom_postman_tests('collection.json')
```

---

### 2. seldom_postman_tester.py（原始版本）

**位置**: 根目录  
**大小**: ~450 行  
**用途**: 原始复杂实现版本

**主要类**:

```python
class PostmanApiParser:
    """与 practical 版本相同"""

class SeldomPostmanTest(seldom.TestCase):
    """基于 Seldom 的 Postman 测试类"""
    - __init__(api_config)     # 初始化
    - test_api_request()       # 执行测试
    - 属性：api_response, api_status_code

class PostmanTestReport:
    """Postman 测试报告生成器"""
    - add_result()             # 添加结果
    - generate_summary()       # 生成摘要
    - generate_html_report()   # 生成 HTML
    - print_console_report()   # 控制台输出

def run_seldom_tests():
    """测试运行函数（手动执行）"""
```

**特点**:
- 📚 更详细的实现
- 🔍 适合学习和研究
- 🛠️ 便于定制和扩展

---

### 3. simple_seldom_tester.py（简化版本）

**位置**: 根目录  
**大小**: ~300 行  
**用途**: 简化版本，直接手动执行

**特点**:
- 📖 代码注释详细
- 🎓 学习教材
- 🔧 易于调试

---

## 📊 关键类和方法

### PostmanApiParser（文件解析器）

```
功能流程：
┌─────────────────────┐
│  load_file()        │  加载并验证 JSON
└──────────┬──────────┘
           │
┌──────────▼──────────┐
│extract_base_url()   │  提取 baseUrl 或从请求推断
└──────────┬──────────┘
           │
┌──────────▼──────────┐
│ extract_apis()      │  递归遍历所有 item
└──────────┬──────────┘
           │
┌──────────▼──────────┐
│ _parse_item()       │  区分文件夹和请求
└──────────┬──────────┘
           │
┌──────────▼──────────┐
│_parse_request()     │  解析具体请求详情
└──────────┬──────────┘
           │
┌──────────▼──────────┐
│  返回 API 列表      │  List[Dict]
└─────────────────────┘
```

**解析流程**：
- 读取 JSON 文件
- 提取变量（如 baseUrl）
- 递归处理文件夹和请求
- 解析 URL、方法、头、体、参数
- 返回结构化的 API 列表

### create_api_test_class（动态类创建）

```
┌──────────────────────┐
│  API Config Dict     │  输入：单个 API 配置
└──────────┬───────────┘
           │
┌──────────▼──────────────┐
│ 定义内部 TestCase 类    │  继承 seldom.TestCase
│ - test_api() 方法       │  实现 HTTP 请求
└──────────┬──────────────┘
           │
┌──────────▼──────────────┐
│  设置类名和元信息       │  APITestCase → TestXXXAPI
└──────────┬──────────────┘
           │
┌──────────▼──────────────┐
│  返回测试类              │  class APITestCase
└──────────────────────────┘
```

### PostmanTestReport（报告生成）

```
结果流程：
┌─────────────────────┐
│  add_result()       │  添加单条结果
│  add_results()      │  批量添加结果
└──────────┬──────────┘
           │
┌──────────▼──────────┐
│generate_summary()   │  计算统计数据
│  - total, passed    │
│  - failed, error    │
│  - success_rate     │
└──────────┬──────────┘
           │
    ┌──────┴────────┐
    │               │
┌───▼────────┐  ┌──▼─────────────┐
│ HTML报告   │  │ 控制台输出      │
└────────────┘  └────────────────┘
```

---

## 🔄 数据流转

### 整个测试流程

```
┌─────────────────────────┐
│  Postman JSON 文件       │
└────────────┬────────────┘
             │
    ┌────────▼────────┐
    │ PostmanApiParser │
    └────────┬────────┘
             │
    ┌────────▼──────────────────┐
    │  API 列表 (List[Dict])     │
    │  [                         │
    │    {name, method, url...}, │
    │    {name, method, url...}  │
    │  ]                         │
    └────────┬──────────────────┘
             │
    ┌────────▼────────────────────┐
    │ 动态创建测试类               │
    │ for each api in apis:       │
    │   create_api_test_class()   │
    └────────┬────────────────────┘
             │
    ┌────────▼─────────────────┐
    │  执行测试                  │
    │  for each TestClass:      │
    │    test_class.test_api()  │
    │    collect result         │
    └────────┬─────────────────┘
             │
    ┌────────▼──────────────────┐
    │  测试结果 (List[Dict])     │
    │  [                         │
    │    {name, status, msg...}, │
    │    {name, status, msg...}  │
    │  ]                         │
    └────────┬──────────────────┘
             │
    ┌────────▼──────────────────┐
    │  报告生成                   │
    │  - HTML 报告               │
    │  - 控制台输出              │
    │  - 统计数据               │
    └───────────────────────────┘
```

---

## 🧩 配置对象结构

### API Config 字典

```python
api_config = {
    'name': str,              # API 名称
    'folder': str,            # 所属文件夹
    'method': str,            # HTTP 方法 (GET/POST/PUT/DELETE/PATCH)
    'url': str,               # 相对路径 URL
    'full_url': str,          # 完整 URL
    'headers': Dict,          # 请求头
    'body': Dict/str/None,    # 请求体
    'params': Dict,           # 查询参数
    'expected_status': int,   # 期望状态码（默认 200）
    'description': str        # 描述信息
}
```

### 测试结果对象

```python
result = {
    'name': str,              # API 名称
    'method': str,            # HTTP 方法
    'url': str,               # 完整 URL
    'status': str,            # 'PASSED'/'FAILED'/'ERROR'
    'message': str,           # 详细信息
    'status_code': int/None,  # 响应状态码
    'folder': str             # 文件夹名称
}
```

---

## 📦 依赖关系

```
requirements.txt
├── seldom>=3.10.0        # 主要测试框架
│   └── requests          # (自动依赖) HTTP 请求库
│   └── unittest          # (内置) 单元测试框架
│   └── logging           # (内置) 日志记录
│
├── requests              # (可选) 直接依赖
└── (其他内置库)
    ├── json              # JSON 解析
    ├── os                # 文件系统操作
    ├── sys               # 系统参数
    ├── datetime          # 时间处理
    ├── re                # 正则表达式
    ├── typing            # 类型提示
    └── urllib.parse      # URL 处理
```

---

## 🎯 扩展点

### 1. 自定义请求处理
修改 `create_api_test_class()` 中的 `test_api()` 方法

### 2. 自定义报告样式
编辑 `PostmanTestReport.generate_html_report()` 中的 HTML 模板

### 3. 增加预处理/后处理
在 API 测试前后添加钩子函数

### 4. 集成 CI/CD
在 `run_seldom_postman_tests()` 中添加集成逻辑

---

## 📝 文件大小参考

| 文件 | 行数 | 大小 | 复杂度 |
|------|------|------|--------|
| practical_seldom_tester.py | ~350 | Low | 中等 |
| seldom_postman_tester.py | ~450 | Medium | 较高 |
| simple_seldom_tester.py | ~300 | Low | 低 |
| demo_seldom_tester.py | ~150 | - | 低 |
| test_seldom_postman.py | ~60 | - | 低 |

---

## 🔗 关键函数调用链

```
main()
 └─ run_seldom_postman_tests(postman_file, base_url)
     ├─ PostmanApiParser(postman_file)
     │   ├─ load_file()
     │   ├─ extract_base_url()
     │   └─ extract_apis()
     │       └─ _parse_item() / _parse_request()
     │
     ├─ create_api_test_class(api) × N
     │   └─ 返回 APITestCase 类
     │
     ├─ for each TestClass:
     │   └─ TestClass().test_api()
     │       ├─ self.get/post/put/delete()
     │       └─ 收集结果
     │
     └─ PostmanTestReport()
         ├─ add_results()
         ├─ generate_html_report()
         └─ print_console_report()
```

---

## 💡 使用推荐

### 新手
1. 运行 `demo_seldom_tester.py` 了解功能
2. 阅读 QUICKSTART.md 快速开始
3. 查看生成的 HTML 报告

### 开发者
1. 学习 practical_seldom_tester.py 实现
2. 查看 test_seldom_postman.py 单元测试
3. 根据需要定制扩展

### 维护者
1. 理解整个项目结构（本文档）
2. 了解 IMPLEMENTATION.md 的方案设计
3. 修改相应模块实现定制需求

---

更多信息请查看其他文档：
- [QUICKSTART.md](QUICKSTART.md) - 快速使用指南
- [IMPLEMENTATION.md](IMPLEMENTATION.md) - 实现方案详解
- [README.md](README.md) - 功能说明