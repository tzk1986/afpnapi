# Postman API 测试工具文档入口（统一目录）

本文档用于交付给其他测试同学时，作为统一入口说明。

## 1. 文档位置统一

当前与 Postman API 测试工具相关的文档（不含报告产物）已统一放在本目录：

- README.md（本文，交付入口）
- 操作手册.md（完整手册）
- 快速命令参考.md（常用命令速查）
- 最终交付清单.md（交付说明）

## 2. 一步一步安装（给新同学）

### 第 1 步：准备 Python

要求：Python 3.10 及以上。

### 第 2 步：进入项目目录

```powershell
cd d:\tangzk\py\seldom-api-testing
```

### 第 3 步：安装依赖

```powershell
pip install -r requirements.txt
```

### 第 4 步：配置地址、Token、报告路径

编辑文件：`postman_api_tester/config.py`

关键配置：

- `BASE_URL`：默认目标服务地址
- `TOKEN`：默认认证 token（可空）
- `REPORT_OUTPUT_DIR`：报告输出目录（可空，空时默认 `项目根目录/reports`）

示例：

```python
BASE_URL = "http://10.50.11.130:11000"
TOKEN = ""
REPORT_OUTPUT_DIR = r"D:\api-test-reports"
```

## 3. 一步一步执行测试

### 方式 A：命令行执行（推荐）

```powershell
python -m postman_api_tester.postman_api_tester "支付（UPS）.postman.json"
```

可选完整参数：

```powershell
python -m postman_api_tester.postman_api_tester <postman_file> [base_url] [output_dir] [token] [results_per_page]
```

说明：

- `output_dir`：本次执行临时覆盖报告目录
- `results_per_page`：报告分页大小

### 方式 B：交互式快速执行

```powershell
python postman_api_tester/run_test_and_open.py
```

脚本会引导你选择：

1. Postman 文件
2. base_url
3. 报告输出目录
4. 每页条数

执行完会自动打开报告中心。

## 4. 查看报告（正式使用）

### 启动报告中心

```powershell
python report_server.py
```

访问：

- 本机：`http://127.0.0.1:5000`
- 局域网：`http://你的IP:5000`

### 报告目录配置一致性

报告中心读取目录优先级：

1. 环境变量 `POSTMAN_REPORTS_DIR`
2. 环境变量 `REPORTS_DIR`
3. `postman_api_tester/config.py` 中 `REPORT_OUTPUT_DIR`
4. 默认 `项目根目录/reports`

这样可以保证“测试执行输出目录”和“报告中心读取目录”一致。

## 5. 打包给其他测试同学的建议

建议打包内容：

- `postman_api_tester/`
- `report_server.py`
- `allow_report_server_firewall.ps1`
- `requirements.txt`
- 需要执行的 `*.postman.json`

首次交付时让对方按本文档第 2、3、4 节逐步执行即可。

## 6. 常见问题

- 报告中心看不到最新报告：确认 `REPORT_OUTPUT_DIR` 与报告中心读取目录一致。
- 局域网打不开：执行 `allow_report_server_firewall.ps1` 放通 5000 端口。
- 中文乱码：PowerShell 先执行 `$env:PYTHONIOENCODING="utf-8"`。
