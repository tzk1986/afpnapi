# Postman API 测试工具文档入口（统一目录）

版本：v1.1.8
发布日期：2026-05-07
文档定位：新人入口，总览目录、安装、配置、首次执行与报告查看。

本版新增重点：修复详情页 GET 实际请求 URL 查询参数重复问题，新增结果详情“标记成功/标记失败/恢复自动结果”人工判定能力；并保持与现有任务队列、报告三件套、历史对比、导出与人工用例能力兼容。

关联文档：

- `postman_api_tester/操作手册.md`：需要完整操作步骤、报告中心说明、故障排查时继续阅读。
- `postman_api_tester/快速命令参考.md`：需要快速执行命令、参数优先级、常见命令示例时优先查看。
- `postman_api_tester/最终交付清单.md`：需要打包交付、对外移交、验收范围时查看。
- `postman_api_tester/开发阅读文档.md`：需要修改代码、确认约束边界、同步开发基线时查看。

本文档用于交付给其他测试同学时，作为统一入口说明。

## 0. 程序目录结构（新人先看）

下面是当前项目中和接口测试、报告中心最相关的目录与文件：

```text
d:/tangzk/py/seldom-api-testing/
├─ postman_api_tester/               # 核心测试模块与文档目录
│  ├─ postman_api_tester.py          # 主执行入口，负责解析 Postman、发请求、生成报告
│  ├─ config.py                      # 地址、Token、超时、报告目录等集中配置
│  ├─ run_test_and_open.py           # 交互式快速启动脚本
│  ├─ README.md                      # 文档总入口（本文）
│  ├─ 操作手册.md                    # 完整操作说明
│  ├─ 快速命令参考.md                # 常用命令速查
│  ├─ 开发阅读文档.md                # 开发约束与版本基线
│  └─ 最终交付清单.md                # 交付时的文件清单
├─ report_server.py                  # 报告中心 Web 服务入口
├─ templates/                        # 外置 HTML 模板（报告首页、数据视图等）
├─ reports/                          # 默认报告输出目录（html/details/meta）
├─ uploaded_collections/             # 报告中心上传执行时保存的 Collection 与导出文件
├─ requirements.txt                  # 依赖安装入口
├─ allow_report_server_firewall.ps1  # Windows 防火墙放通 5000 端口脚本
├─ sample_api_collection.json        # 示例 Collection
├─ _smoke_test.py                    # 冒烟测试脚本（验证核心能力是否正常）
└─ 其他业务/测试目录                  # 如 api_object/、test_data/、test_dir/ 等
```

建议新人先建立下面这层认知：

- `postman_api_tester/` 是测试执行核心和文档中心。
- `report_server.py` 是报告查看入口，不负责发起测试，只负责展示、对比、导出、重试。
- `templates/` 是报告中心页面模板，页面显示问题优先看这里。
- `reports/` 是测试执行后的默认产物目录，报告中心默认也从这里读数据。
- `uploaded_collections/` 是通过报告中心网页上传执行时产生的中间文件目录。

## 1. 文档位置统一

当前与 Postman API 测试工具相关的文档（不含报告产物）已统一放在本目录：

- README.md（本文，交付入口）
- 开发阅读文档.md（开发前必读 + 约束汇总 + 更新命令）
- 操作手册.md（完整手册）
- 快速命令参考.md（常用命令速查）
- 最终交付清单.md（交付说明）

### 文档阅读顺序

如果你是第一次接手这个项目，建议按下面顺序阅读：

1. `README.md`
	先建立目录结构、安装步骤、首次执行和报告查看的整体认知。
2. `操作手册.md`
	在已经知道整体路径后，继续看完整操作流程、报告中心说明和故障排查。
3. `快速命令参考.md`
	在实际执行时，直接查常用命令、参数写法和优先级规则。
4. `最终交付清单.md`
	在需要打包给其他同学、做交付说明或验收时查看。
5. `开发阅读文档.md`
	只有在准备改代码、调整默认行为或确认约束边界时再进入这份文档。

## 2. 一步一步安装（给新同学）

### 第 0 步：先把代码拉到本地

如果是 Git 仓库拉取，建议放到固定开发目录，例如：

```powershell
git clone <你的仓库地址> d:\tangzk\py\seldom-api-testing
cd d:\tangzk\py\seldom-api-testing
```

如果不是 Git 拉取，而是直接收到压缩包，也建议解压到类似目录后再执行下面步骤。

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
- `ENABLE_SELECTIVE_RUN`：是否启用“导入后仅执行已选接口”能力
- `ENABLE_ADHOC_RUN`：是否启用首页“新增接口测试”独立页面入口
- `ADHOC_MAX_ITEMS`：单次 ad-hoc 任务允许录入的最大接口数
- `ADHOC_DEFAULT_COLLECTION_NAME`：ad-hoc 临时任务默认集合名称
- `REPORT_EXPORT_DEFAULT_SCOPE`：报告导出默认范围（`full` / `report_only`）

示例：

```python
BASE_URL = "http://10.50.11.130:11000"
TOKEN = ""
REPORT_OUTPUT_DIR = r"D:\api-test-reports"
```

建议按下面顺序配置：

1. 先改 `BASE_URL`，确保指向当前测试环境。
2. 如果接口必须登录，再决定是直接填 `TOKEN`，还是留空让程序自动登录获取。
3. 如果团队希望把报告统一输出到固定目录，再改 `REPORT_OUTPUT_DIR`。
4. 如需调整请求等待时间，可继续看 `REQUEST_CONNECT_TIMEOUT` 和 `REQUEST_READ_TIMEOUT`。

如果不想改代码文件，也可以用环境变量临时覆盖：

```powershell
$env:POSTMAN_BASE_URL = "http://10.50.11.130:11000"
$env:POSTMAN_TOKEN = "your_token"
python -m postman_api_tester.postman_api_tester "sample_api_collection.json"
```

## 3. 一步一步执行测试

推荐新人的最短上手路径：

1. 先修改 `postman_api_tester/config.py` 中的 `BASE_URL`。
2. 准备一个可执行的 `*.postman.json` 文件。
3. 用命令行跑一次测试，确认能生成报告。
4. 再启动 `report_server.py` 查看结果和失败详情。

### 方式 A：命令行执行（推荐）

```powershell
python -m postman_api_tester.postman_api_tester "支付（UPS）.postman.json"
```

如果只是第一次验证环境是否打通，建议直接用示例文件或一份最小 Collection 先跑通，不要一开始就执行几百个接口。

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

页面里常见入口含义：

- `报告中心首页`：查看历史报告、删除报告、做差异对比。
- `上传并执行`：支持先解析集合接口，再选择“全量执行”或“仅执行已选接口”。
- `新增接口测试`：在首页点击入口按钮后进入独立页面，录入接口（名称/目录/方法/URL/Headers/Params/Body）并执行生成报告，无需先准备完整 Collection 文件。
- `数据视图`：按接口逐条查看请求头、参数、响应体、错误信息。
- `人工用例编辑器`：按三段式流程新增/编辑人工用例（先发送请求，再确认 PASSED/FAILED，再保存）。
- `编辑器切换与 Body 选择`：mc 与 er 双编辑器互相隔离，Body 类型切换互不污染；支持 none/raw/urlencoded/formdata/graphql/binary 切换。
- `导入执行一致性`：针对导出后二次导入场景，`request.url` 仅含 `raw`（缺少 `path`）时也可被正确解析并执行，避免“预览 2 条、执行 1 条”。
- `导出参数完整性`：导出人工用例时保留完整请求参数（headers/params/body/body_mode/body_data），避免导入后请求体为空或参数缺失。
- `结果行内排除`：在结果列表直接执行“排除/取消排除”，无需先打开详情弹窗。
- `详情人工判定`：结果详情支持“标记成功/标记失败/恢复自动结果”，可在不重发请求时修正状态并回写 summary。
- `实际URL去重`：当配置 URL 已含 query 且 params 也有同名参数时，详情“实际请求 URL”按去重合并规则展示，不再重复拼接。
- `原始 HTML`：打开生成时的原始静态报告。
- `查看元数据`：查看当前报告的结构化摘要与结果索引。
- `导出最新 JSON`：支持按全量导出或仅导出“本次报告涉及接口”。
- `导出范围选择`：`full` 适合完整回归；`report_only` 适合最小复现。本次报告已覆盖全量时，两者导出内容可能一致，页面会提示“范围等价”。

ad-hoc 直接新增接口测试补充：

- 无需先上传 Collection 文件，首页点击“打开新增接口测试页”后，在独立页面录入 1..N 条接口即可入队执行。
- URL 支持绝对 `http/https` 地址、`{{baseUrl}}/...` / `{{base_url}}/...` 变量地址，或配合 `base_url` 的相对路径。
- 单次任务接口数量上限由 `postman_api_tester/config.py` 的 `ADHOC_MAX_ITEMS` 控制，默认集合名由 `ADHOC_DEFAULT_COLLECTION_NAME` 提供。
- 后端通过 `/api/run-ad-hoc-tests` 接收 JSON 请求，内部会先生成临时 Collection 文件到 `uploaded_collections/`，再复用既有任务队列与状态轮询链路。

补充说明：

- 人工用例“发送请求”由后端代理接口处理，仅允许 `http/https` 协议。
- 编辑重试接口 `/re-request-api` 与代理接口口径一致，均仅允许 `http/https` 协议。
- 代理请求超时统一读取 `postman_api_tester/config.py`（`REQUEST_CONNECT_TIMEOUT`、`REQUEST_READ_TIMEOUT`）。

运行验证脚本（可复用）：

- `python test_data/smoke_report_server_20260427.py`

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

## 6. 新人第一次使用的推荐顺序

如果你是第一次接手这个项目，建议按下面顺序操作：

1. 先看本文第 0 节目录结构，知道“测试执行”和“报告查看”分别在哪。
2. 再改 `postman_api_tester/config.py` 的 `BASE_URL` / `TOKEN` / `REPORT_OUTPUT_DIR`。
3. 执行 `pip install -r requirements.txt` 安装依赖。
4. 用一份最小 `*.postman.json` 跑命令行测试。
5. 确认 `reports/` 或你配置的目录下生成了 `.html`、`_details.json`、`_meta.json` 三件套。
6. 启动 `python report_server.py`，再从浏览器进入报告中心查看结果。
7. 若要给其他机器访问，再执行 `allow_report_server_firewall.ps1`。

## 7. 常见问题

- 报告中心看不到最新报告：确认 `REPORT_OUTPUT_DIR` 与报告中心读取目录一致。
- 局域网打不开：执行 `allow_report_server_firewall.ps1` 放通 5000 端口。
- 中文乱码：PowerShell 先执行 `$env:PYTHONIOENCODING="utf-8"`。
