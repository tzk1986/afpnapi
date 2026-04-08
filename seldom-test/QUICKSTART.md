# 快速使用指南

基于 Seldom 框架的 Postman API 测试工具 - 5分钟快速入门

## 📦 安装

### 1. 安装依赖

```bash
cd seldom-test
pip install -r requirements.txt
```

### 2. 验证安装

```bash
python -c "import seldom; print(f'Seldom {seldom.__version__} installed successfully')"
```

## 🚀 快速开始

### 方案一：最简单的方式（推荐）

使用演示脚本查看完整功能：

```bash
python demo_seldom_tester.py
```

输出示例：
```
✓ 成功加载 2 个API接口
✓ HTML报告已生成: demo_report_20260408_095029.html
✓ 控制台报告已生成
```

### 方案二：使用自己的 Postman 文件

```bash
# 基本使用
python practical_seldom_tester.py your_postman_collection.json

# 指定自定义 URL
python practical_seldom_tester.py your_postman_collection.json https://api.example.com

# 指定报告输出目录
python practical_seldom_tester.py your_postman_collection.json https://api.example.com ./my_reports
```

### 方案三：在 Python 代码中使用

```python
from practical_seldom_tester import run_seldom_postman_tests

# 运行测试
results = run_seldom_postman_tests(
    postman_file='your_postman_collection.json',
    base_url='https://api.example.com',  # 可选
    output_dir='./reports'                # 可选
)

# results 是测试结果列表
for result in results:
    print(f"{result['name']}: {result['status']}")
```

## 📊 查看测试报告

### HTML 报告
测试报告自动保存为 HTML 文件在 `../reports` 目录：
```
reports/
├── seldom_postman_report_20260408_095000.html
├── seldom_postman_report_20260408_095030.html
└── ...
```

直接用浏览器打开查看详细的图表和统计信息。

### 控制台输出
测试完成后会在控制台显示：
```
================================================================================
                            Postman API 测试报告                         

================================================================================

总计: 5 | 通过: 5 | 失败: 0 | 错误: 0
成功率: 100.00% | 耗时: 2.34s
```

## 📚 常见用法

### 1. 测试特定的 Postman 集合

```python
from seldom_postman_tester import PostmanApiParser

# 仅解析不执行
parser = PostmanApiParser('my_api.json')
apis = parser.extract_apis()

print(f"发现 {len(apis)} 个 API")
for api in apis:
    print(f"- {api['name']}: {api['method']} {api['url']}")
```

### 2. 单位测试

```bash
python test_seldom_postman.py
```

### 3. 查看使用示例

```bash
python seldom_examples.py
```

## 🔧 配置

### 修改基础 URL

**方式1：命令行参数**
```bash
python practical_seldom_tester.py collection.json https://staging.api.com
```

**方式2：Postman 文件中配置**
在 Postman 中设置 `baseUrl` 变量

**方式3：代码中配置**
```python
run_seldom_postman_tests('collection.json', base_url='https://custom.com')
```

### 修改报告输出目录

```bash
python practical_seldom_tester.py collection.json https://api.com ./my_reports
```

## 📝 支持的 HTTP 方法

- ✅ GET
- ✅ POST
- ✅ PUT
- ✅ DELETE
- ✅ PATCH

## 🎯 文件说明

| 文件 | 用途 | 推荐使用场景 |
|------|------|-----------|
| `practical_seldom_tester.py` | 主要实现 | 生产环境使用 |
| `demo_seldom_tester.py` | 功能演示 | 学习/演示 |
| `simple_seldom_tester.py` | 简化版本 | 手动调试 |
| `seldom_postman_tester.py` | 原始版本 | 深度定制 |
| `test_seldom_postman.py` | 单元测试 | 验证功能 |

## 🐛 常见问题

### Q1: 如何修改超时时间？
编辑对应的 Python 文件，找到 Seldom 配置部分，修改 timeout 参数。

### Q2: 支持认证吗？
支持。在 HTTP 请求头中添加认证信息（如 Authorization、API Key 等）。

### Q3: 能否跳过某些 API 测试？
可以。修改 Postman 集合文件，禁用相应的请求或文件夹。

### Q4: 并发执行支持吗？
当前是串行执行。如需并发，可使用 seldom 的高级配置。

## 💡 提示

- 确保 Postman JSON 文件格式正确
- 建议先运行 `demo_seldom_tester.py` 了解功能
- 查看生成的 HTML 报告获得详细信息
- 遇到问题查看 README.md 和其他文档

## 📖 更多信息

- [详细使用文档](README.md)
- [项目结构说明](PROJECT_STRUCTURE.md)
- [方案实现方式](IMPLEMENTATION.md)
- [Seldom 官方文档](https://github.com/SeldomQA/seldom)