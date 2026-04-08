# Seldom Postman API Tester

基于 [Seldom](https://github.com/SeldomQA/seldom) 框架的 Postman API 测试工具。

## 📚 文档导航

- ⭐ **[快速开始](QUICKSTART.md)** - 5 分钟快速入门
- 📖 **[项目结构](PROJECT_STRUCTURE.md)** - 深入理解代码组织
- 🏗️ **[实现方案](IMPLEMENTATION.md)** - 技术方案详解
- 📑 **[文档索引](INDEX.md)** - 完整文档目录

## 特性

- ✅ 基于 Seldom 测试框架
- ✅ 支持 Postman Collection JSON 文件
- ✅ 自动解析 API 接口信息
- ✅ 生成 HTML 测试报告
- ✅ 控制台测试结果输出
- ✅ 支持自定义基础URL
- ✅ 解决 Seldom 框架属性冲突问题

## 安装依赖

```bash
pip install -r requirements.txt
```

## 使用方法

### 1. 基本使用

```python
from practical_seldom_tester import run_seldom_postman_tests

# 运行 Postman 测试
results = run_seldom_postman_tests('path/to/your/postman_collection.json')
```

### 2. 命令行使用

```bash
# 基本使用
python practical_seldom_tester.py your_postman_file.json

# 指定基础URL
python practical_seldom_tester.py your_postman_file.json https://api.example.com

# 指定报告输出目录
python practical_seldom_tester.py your_postman_file.json https://api.example.com ./reports
```

### 3. 高级用法

```python
from seldom_postman_tester import PostmanApiParser, create_api_test_class
import seldom

# 解析 Postman 文件
parser = PostmanApiParser('your_postman_file.json')
apis = parser.extract_apis()

# 创建测试类
test_classes = []
for api in apis:
    test_class = create_api_test_class(api)
    test_classes.append(test_class)

# 使用 Seldom 运行测试
seldom.main(case=test_classes, report="custom_report.html")
```

## 文件说明

- `practical_seldom_tester.py` - 主要测试执行文件
- `simple_seldom_tester.py` - 简化版本（手动执行）
- `seldom_postman_tester.py` - 原始复杂版本（动态类创建）
- `seldom_examples.py` - 使用示例
- `test_seldom_postman.py` - 单元测试

## 解决的问题

### Seldom 框架属性冲突

Seldom 的 `TestCase` 类中 `response` 和 `status_code` 是只读属性，不能直接赋值。

**解决方案：**
- 使用 `api_response` 和 `api_status_code` 作为替代属性名
- 通过 Seldom 的 `self.response` 和 `self.response.status_code` 访问数据

### 动态测试类创建

为了充分利用 Seldom 的测试运行机制，实现了动态创建测试类的功能。

## 示例输出

```
开始加载Postman文件: sample_api_collection.json
✓ 成功加载 5 个API接口
  基础URL: https://httpbin.org

创建了 5 个测试类

开始使用 Seldom 框架执行测试...
2024-11-19 20:30:00 - INFO - Start to run test case...
2024-11-19 20:30:01 - INFO - test_api (TestGetUser) ... ok
2024-11-19 20:30:02 - INFO - test_api (TestCreateUser) ... ok
...

测试完成!
总计: 5 个API测试
通过: 5, 失败: 0
✓ HTML报告已保存: reports/seldom_postman_report_20241119_203000.html
```

## 依赖项

- `seldom>=3.10.0` - 测试框架
- `requests` - HTTP 请求库（由 seldom 自动安装）

## 注意事项

1. 确保 Postman JSON 文件格式正确
2. 如果使用自定义基础URL，会覆盖文件中的配置
3. 测试报告默认保存在 `../reports` 目录
4. Seldom 会自动处理 HTTP 请求和响应验证