# Postman API 测试工具 - 快速启动指南

## 🚀 5分钟快速开始

### 第一步：准备Postman文件

从APIFox/Postman导出接口集合为JSON文件：

1. 打开APIFox或Postman
2. 右键点击集合 → **导出** 
3. 选择 **Postman(Collection v2.1)** 格式
4. 保存文件（例如：`api_collection.json`）

### 第二步：运行测试

#### 方式A - 最简单（命令行）
```bash
python postman_api_tester.py api_collection.json
```

#### 方式B - 指定基础URL
```bash
python postman_api_tester.py api_collection.json https://your-api.com
```

#### 方式C - Python代码
```python
from postman_api_tester import run_postman_tests

report = run_postman_tests('api_collection.json')
```

### 第三步：查看结果

✅ **控制台输出** - 立即显示测试摘要
✅ **HTML报告** - 保存在 `./reports/postman_report_YYYYMMDD_HHMMSS.html`

---

## 📋 常用命令速查表

| 任务 | 命令 |
|------|------|
| 运行所有测试 | `python postman_api_tester.py api.json` |
| 指定API地址 | `python postman_api_tester.py api.json https://api.example.com` |
| 自定义报告目录 | `python postman_api_tester.py api.json https://api.example.com ./my_reports` |
| 验证功能 | `python test_postman_api_tester.py` |
| 查看使用示例 | `python postman_api_tester_examples.py` |

---

## 📁 文件结构说明

```
.
├── postman_api_tester.py              # ⭐ 核心模块
├── postman_api_tester_examples.py     # 📖 使用示例代码
├── test_postman_api_tester.py         # ✓ 功能验证脚本
├── POSTMAN_API_TESTER_README.md       # 📚 完整文档
├── QUICK_START.md                     # 🚀 本文件
├── reports/                           # 📊 测试报告输出目录
│   └── postman_report_20240115_103045.html
└── api_collection.json                # Postman导出文件（示例）
```

---

## 🎯 常见用例

### 用例1：基本测试
```bash
python postman_api_tester.py my_api_collection.json
```
✅ 读取集合中所有接口
✅ 执行所有测试
✅ 生成报告

### 用例2：针对不同环境测试
```bash
# 测试开发环境
python postman_api_tester.py api.json https://dev.example.com ./reports/dev

# 测试测试环境
python postman_api_tester.py api.json https://test.example.com ./reports/test

# 测试生产环境
python postman_api_tester.py api.json https://api.example.com ./reports/prod
```

### 用例3：Python代码集成
```python
from postman_api_tester import run_postman_tests

# 执行测试
report = run_postman_tests(
    postman_file='api.json',
    base_url='https://api.example.com',
    output_dir='./reports'
)

# 获取摘要
summary = report.generate_summary()
print(f"成功率: {summary['success_rate']}")
```

### 用例4：自定义过滤执行
```python
from postman_api_tester import PostmanApiParser, PostmanTestExecutor, PostmanTestReport

parser = PostmanApiParser('api.json')
apis = parser.extract_apis()

# 只测试GET请求
get_apis = [api for api in apis if api['method'] == 'GET']

report = PostmanTestReport()
for api in get_apis:
    executor = PostmanTestExecutor(api)
    executor.start()
    result = executor.execute_test()
    report.add_result(result)

report.print_console_report()
```

---

## 🔧 故障排除

### 问题1：ModuleNotFoundError: No module named 'seldom'

**解决方案：** 安装依赖
```bash
pip install -r requirements.txt
```

### 问题2：文件编码错误

**解决方案：** 确保Postman文件使用UTF-8编码
```bash
file -i api_collection.json  # Linux/Mac
```

### 问题3：网络连接错误

**解决方案：** 检查API地址和网络连接
```bash
# 测试连接
ping api.example.com
curl https://api.example.com
```

### 问题4：响应状态码不符合预期

**解决方案：** 
- 检查API是否需要认证头
- 验证请求参数是否正确
- 在Postman软件中手动测试

---

## 📊 测试报告说明

### 控制台输出示例
```
================================================================================
                          Postman API 测试报告
================================================================================

总计: 50 | 通过: 48 | 失败: 2 | 错误: 0
成功率: 96.00% | 耗时: 12.34s

[✓] Get User List                  | GET    | PASSED  | 200
[✓] Create User                    | POST   | PASSED  | 201
[✗] Delete Non-existent User       | DELETE | FAILED  | 404
[!] Internal Server Error          | POST   | ERROR   | 500

================================================================================
```

### HTML报告包含
- 📊 测试摘要（总数、通过率、耗时）
- 📋 详细结果表格（API名称、方法、URL、状态、状态码）
- 🎨 美观的样式和响应式设计
- ⏱️ 测试开始和结束时间

---

## 💡 提示和最佳实践

### ✅ 推荐做法

1. **定期更新Postman文件**
   ```bash
   # 从APIFox定期导出最新的接口定义
   ```

2. **按环境分类测试**
   ```bash
   # 分别测试dev、test、prod环境
   for env in dev test prod; do
     python postman_api_tester.py api.json https://$env.example.com ./reports/$env
   done
   ```

3. **集成到CI/CD流程**
   - GitHub Actions
   - Jenkins
   - GitLab CI/CD

4. **版本控制报告**
   ```bash
   git add reports/
   git commit -m "API测试报告"
   ```

5. **设置失败告警**
   ```bash
   if ! python postman_api_tester.py api.json https://api.example.com; then
     echo "API测试失败" | mail -s "Alert" admin@example.com
   fi
   ```

### ❌ 避免做法

- 不要在测试中硬编码密钥和token
- 不要测试生产环境的破坏性操作（DELETE、PUT）
- 不要忽略超时和网络异常处理
- 不要跳过错误日志的检查

---

## 🔐 安全建议

### 处理敏感信息
```python
# 使用环境变量而不是硬编码
import os
api_key = os.getenv('API_KEY')

# 在Postman中使用变量
"Authorization": "Bearer {{apiKey}}"
```

### 避免日志泄露
```python
# 敏感数据不要出现在报告中
# 检查response_data中是否包含密钥等信息
```

---

## 📈 进阶功能

### 扩展自定义验证
```python
# 在PostmanTestExecutor中添加自定义验证逻辑
class CustomExecutor(PostmanTestExecutor):
    def execute_test(self):
        result = super().execute_test()
        
        # 自定义验证
        if self.response_data.get('error'):
            result['status'] = 'FAILED'
        
        return result
```

### 性能测试集成
```python
# 记录响应时间
result['response_time'] = response.elapsed.total_seconds()

# 检查是否超过阈值
if result['response_time'] > 1.0:
    result['status'] = 'SLOW'
```

### 数据驱动测试
```python
# 从CSV/JSON读取测试数据
import csv

with open('test_data.csv') as f:
    reader = csv.DictReader(f)
    for row in reader:
        api['body'] = row
        # 执行测试
```

---

## 🤝 获取帮助

### 查看更多示例
```bash
python postman_api_tester_examples.py
```

### 查看完整文档
