# 阶段 0：边界梳理与依赖冻结

**完成日期**：2026-05-11  
**覆盖范围**：postman_api_tester.py、report_server.py、所有共享模块  
**目标**：清晰界定可拆分模块、依赖关系、函数签名、职责边界

---

## 一、入口分析

### 1.1 postman_api_tester.py 对外入口

| 入口类型 | 函数/类 | 签名 | 用途 | 是否公开 |
|---------|--------|------|------|---------|
| 函数 | `run_postman_tests()` | 10 参数 | 主执行入口，报告服务端调用 | ✅ 公开 |
| 类 | `PostmanTestReport` | - | 报告数据结构，服务端依赖 | ✅ 公开 |
| CLI | `__main__` | - | 命令行入口 | ✅ 公开 |
| 导入（`__init__.py`） | 4 个符号导出 | - | 包级接口 | ✅ 公开 |

**关键约束**：
- `run_postman_tests()` 签名必须保持不变（报告服务端 832 行调用）
- `PostmanTestReport` 的属性与公开方法不可改变
- CLI 入口的参数解析不可改变

### 1.2 report_server.py 对外入口

| 入口类型 | 接口/类 | 用途 | 依赖入参 |
|---------|--------|------|---------|
| Flask 路由 | 25+ 个 HTTP 端点 | Web 前端调用 | JSON 请求体 |
| 模块初始化 | `app` Flask 应用 | 外部启动入口 | - |
| 后台 Worker | `run_postman_job()` 函数 | 被 threading.Thread 调用 | 4 个参数 |

**关键约束**：
- 所有路由的 HTTP 契约（输入/输出 JSON 格式）必须保持不变
- Worker 函数签名必须保持不变（被 threading.Thread 调用）

---

## 二、模块职责边界

### 2.1 执行链路（Execution Path）

**定义**：从 Collection 解析 → 认证 → 单接口执行 → 结果收集，全程由 postman_api_tester.py 与其内部模块负责

**主要模块**：
- `parser.py` - Collection 解析（PostmanApiParser）
- `executor.py` - 单接口执行（PostmanTestExecutor）
- `auth.py` - 认证与 token 获取（get_auth_token）
- `session.py` - 会话管理（create_shared_session）
- `db_feedback.py` - 错误诊断（尚未完全独立）
- `postman_api_tester.py` - 编排层（run_postman_tests）

**特征**：
- 无 Flask 依赖
- 无文件 I/O（除了读取 JSON 输入）
- 无全局任务状态（会话与认证为局部变量）
- 返回值为 PostmanTestReport 对象

### 2.2 报告链路（Report Path）

**定义**：从磁盘读取报告 → 查询、转换、呈现 → JSON 返回给前端

**主要模块**：
- `report_repository.py` - 报告元数据与详情加载
- `report_query_service.py` - 报告数据过滤、分页、比较
- `report_results_service.py` - 响应 Payload 构建（21 个 build_* 函数）
- `report_junit_service.py` - JUnit XML 生成
- `report_retry_service.py` - 重试 job plan 构建

**特征**：
- 纯函数为主（无状态修改）
- 负责数据形状转换（Dict → Dict）
- 部分涉及磁盘 I/O（报告读取）
- 无网络请求

### 2.3 路由层（Route Layer）

**定义**：Flask 路由，负责 HTTP 入参校验、服务调用、响应返回

**位置**：report_server.py 的 @app.route 装饰器区块（第 1946-2889 行）

**特征**：
- 依赖 Flask request、jsonify 等
- 触发执行链路或报告链路
- 管理后台任务队列（RUN_JOBS）

---

## 三、共享工具函数清单

### 3.1 URL 处理工具

| 函数 | 位置 | 签名 | 职责 | 复用度 | 拆分难度 |
|------|------|------|------|--------|---------|
| `normalize_url_and_params()` | runtime_utils.py | (url: str, params: Dict) → (url, params) | URL 与参数标准化 | 高（6 处）| ⭐ 低 |
| `merge_url_with_params()` | runtime_utils.py | (url: str, params: Dict) → str | URL 与参数合并 | 中（3 处）| ⭐ 低 |

**评价**：已独立，可直接迁移

### 3.2 脱敏工具

| 函数 | 位置 | 签名 | 职责 | 复用度 | 拆分难度 |
|------|------|------|------|--------|---------|
| `strip_auth_headers()` | report_server_utils.py | (headers: Dict) → Dict | 删除敏感头 | 高（8 处）| ⭐ 低 |

**评价**：已独立，可直接迁移

### 3.3 文件与路径工具

| 函数 | 位置 | 签名 | 职责 | 复用度 | 拆分难度 |
|------|------|------|------|--------|---------|
| `safe_report_artifact()` | report_server_utils.py | (name: str, ext: str) → str | 安全文件名生成 | 中（4 处）| ⭐ 低 |
| `sanitize_export_name()` | report_server_utils.py | (name: str) → str | 导出文件名清理 | 低（1 处）| ⭐ 低 |
| `checkpoint_file_path()` | runtime_utils.py | (job_id: str, dir: str) → Path | checkpoint 路径生成 | 低（2 处）| ⭐ 低 |

**评价**：已独立，可直接迁移

### 3.4 JSON 与数据处理

| 函数 | 位置 | 签名 | 职责 | 复用度 | 拆分难度 |
|------|------|------|------|--------|---------|
| `to_bool()` | report_server_utils.py | (value: Any) → bool | 字符串转布尔值 | 中（5 处）| ⭐ 低 |
| `normalize_exclusion_key()` | report_server_utils.py | (key: str) → str | 排除键格式标准化 | 高（6 处）| ⭐ 低 |
| `build_exclusion_key()` | report_server_utils.py | (...) → str | 排除键生成 | 中（3 处）| ⭐ 低 |
| `result_exclusion_key()` | report_server_utils.py | (result: Dict) → str | 结果排除键提取 | 中（4 处）| ⭐ 低 |

**评价**：已独立，可直接迁移

---

## 四、高复用内部函数清单（report_server.py）

### 4.1 集合与用例处理

| 函数 | 行数 | 职责 | 调用方 | 状态 | 拆分难度 | 推荐拆分 |
|------|------|------|--------|------|---------|---------|
| `_extract_collection_preview_items()` | 250 | Collection 预览项提取 | 1 处（2063 行） | 🟡 内部辅助 | ⭐ 低 | 可拆至 utils/ |
| `_normalize_adhoc_case()` | 362 | Ad-hoc 用例标准化 | 3 处 | 🟡 内部辅助 | ⭐ 低 | 可拆至 utils/ |
| `_build_adhoc_collection()` | 427 | Ad-hoc Collection 构建 | 2 处（2813 行） | 🟡 内部辅助 | ⭐⭐ 中低 | 可拆至 handlers/ |
| `_remove_excluded_items()` | 467 | 排除项移除 | 2 处 | 🟡 内部辅助 | ⭐⭐ 中低 | 可拆至 utils/ |
| `_append_manual_cases_to_collection()` | 515 | 手工用例追加 | 2 处 | 🟡 内部辅助 | ⭐⭐ 中低 | 可拆至 utils/ |
| `_parse_selected_item_paths()` | 788 | 选中项路径解析 | 2 处 | 🟡 内部辅助 | ⭐ 低 | 可拆至 utils/ |

### 4.2 HTTP 请求与响应处理

| 函数 | 行数 | 职责 | 调用方 | 状态 | 拆分难度 | 推荐拆分 |
|------|------|------|--------|------|---------|---------|
| `_item_by_path()` | 1008 | Collection 中按路径查找项 | 内部辅助 | 🟡 | ⭐⭐ | 可拆至 utils/ |
| `_find_item_fallback()` | 1032 | 项查找备选方案 | 2 处 | 🟡 | ⭐⭐ | 可拆至 utils/ |
| `_set_request_url()` | 1054 | 请求 URL 设置 | 1 处（1253 行） | 🟡 | ⭐ | 可拆至 utils/ |
| `_set_request_headers()` | 1066 | 请求头设置 | 1 处（1253 行） | 🟡 | ⭐ | 可拆至 utils/ |
| `_normalize_urlencoded_rows()` | 1072 | URL-encoded 行标准化 | 1 处（1174 行） | 🟡 | ⭐ | 可拆至 utils/ |
| `_normalize_formdata_rows()` | 1094 | Form-data 行标准化 | 1 处（1174 行） | 🟡 | ⭐ | 可拆至 utils/ |
| `_normalize_graphql_data()` | 1122 | GraphQL 数据标准化 | 1 处（1174 行） | 🟡 | ⭐ | 可拆至 utils/ |
| `_infer_body_mode_from_stored_body()` | 1139 | 存储的请求体推断 body_mode | 1 处（1174 行） | 🟡 | ⭐ | 可拆至 utils/ |
| `_set_request_body()` | 1174 | 请求体设置 | 1 处（1253 行） | 🟡 | ⭐⭐ | 可拆至 utils/ |
| `_build_request_kwargs()` | 1253 | requests.request 参数构建 | 1 处（1359 行）| 🟡 | ⭐⭐ | 可拆至 utils/ |
| `_execute_http_request()` | 1359 | **[NEW Slice 4]** HTTP 请求执行 | 2 处（2542, 2654） | ✅ 独立 | ⭐⭐ | 可拆至 utils/ |

### 4.3 报告与结果处理

| 函数 | 行数 | 职责 | 调用方 | 状态 | 拆分难度 | 推荐拆分 |
|------|------|------|--------|------|---------|---------|
| `_collect_report_item_paths()` | 1472 | 报告中的项路径收集 | 1 处 | 🟡 | ⭐ | 可拆至 utils/ |
| `_prune_collection_to_paths()` | 1480 | Collection 按路径裁剪 | 2 处 | 🟡 | ⭐⭐ | 可拆至 utils/ |
| `_iter_request_items()` | 1514 | Collection 遍历所有请求项 | 2 处 | 🟡 | ⭐ | 可拆至 utils/ |
| `_extract_msg_errcode()` | 1534 | 响应体中提取 msg/errCode | 3 处 | 🟡 | ⭐ | 可拆至 utils/ |
| `_compute_summary()` | 1562 | 报告摘要计算 | 1 处 | 🟡 | ⭐ | 可拆至 utils/ |
| `_update_report_meta()` | 1572 | 报告元数据更新 | 8 处 | 🟡 | ⭐⭐⭐ | 保留（涉及磁盘 I/O） |

### 4.4 Job 入队与 Worker（已在 Slice 3-5 整合）

| 函数 | 行数 | 职责 | 调用方 | 状态 | 拆分难度 | 推荐拆分 |
|------|------|------|--------|------|---------|---------|
| `_enqueue_retry_job()` | 885 | **[NEW Slice 3]** 重试 job 入队 | 2 处 | ✅ 独立 | ⭐⭐ | 已整合到 handler |
| `_enqueue_job_with_worker()` | 908 | **[NEW Slice 5]** 通用 job 入队 | 2 处 | ✅ 独立 | ⭐⭐ | 已整合到 handler |
| `_report_list_item()` | 955 | 报告列表项格式化 | 1 处 | 🟡 | ⭐ | 可拆至 utils/ |
| `_build_preview_url()` | 978 | 预览 URL 构建 | 2 处 | 🟡 | ⭐ | 可拆至 utils/ |

### 4.5 配置读取（已有统一接口）

| 函数 | 行数 | 职责 | 复用度 | 拆分难度 | 推荐拆分 |
|------|------|------|--------|---------|---------|
| `_cfg_int()` | 101 | 读取整数配置 | 高（20+ 处） | ⭐ | 已有专属函数 |
| `_cfg_bool()` | 110 | 读取布尔配置 | 高（20+ 处） | ⭐ | 已有专属函数 |
| `_cfg_str()` | 124 | 读取字符串配置 | 中（10+ 处） | ⭐ | 已有专属函数 |
| `_cfg_dict()` | 164 | 读取字典配置 | 低（2 处） | ⭐ | 已有专属函数 |

**评价**：统一配置接口已建立，可保持原样

---

## 五、核心依赖关系图

```
postman_api_tester.py (执行链路 - 无 Flask 依赖)
  ├─ PostmanApiParser (parser.py)
  ├─ PostmanTestExecutor (executor.py)
  ├─ get_auth_token (auth.py)
  ├─ create_shared_session (session.py)
  └─ runtime_utils.* (checkpoint, fingerprint 等)

report_server.py (路由 + 后台 worker)
  ├─ postman_api_tester.run_postman_tests (执行链路入口)
  ├─ report_repository.* (报告读取)
  ├─ report_query_service.* (报告查询)
  ├─ report_results_service.* (响应构建)
  ├─ report_retry_service.* (重试逻辑)
  ├─ report_junit_service.* (JUnit 生成)
  ├─ report_server_utils.* (通用脱敏、格式化)
  ├─ runtime_utils.* (URL 处理、checkpoint)
  └─ 私有 helper 函数 (50+ 个，可拆分至 utils/)

路由依赖后台 worker (run_postman_job):
  └─ postman_api_tester.run_postman_tests
```

---

## 六、可拆分项清单（按优先级排序）

### 优先级 P1：最稳定的纯函数（无状态、无副作用）

| 类别 | 函数 | 位置 | 签名稳定性 | 目标位置 | 预计工作量 |
|------|------|------|----------|---------|-----------|
| 工具 | `_normalize_*()` 等 URL 处理 | report_server.py | ✅ 稳定 | utils/url_utils.py | 15 分钟 |
| 工具 | `_set_request_*() / _build_request_kwargs()` | report_server.py | ✅ 稳定 | utils/request_builder.py | 30 分钟 |
| 工具 | `_extract_msg_errcode()` | report_server.py | ✅ 稳定 | utils/response_parser.py | 10 分钟 |
| 工具 | `_compute_summary()` | report_server.py | ✅ 稳定 | utils/report_utils.py | 10 分钟 |

**统计**：4 个小型 utils 模块，共 65 分钟

### 优先级 P2：Collection 与用例处理（中等复杂度）

| 类别 | 函数 | 位置 | 签名稳定性 | 目标位置 | 预计工作量 |
|------|------|------|----------|---------|-----------|
| 用例 | `_normalize_adhoc_case()` | report_server.py | ✅ 稳定 | handlers/adhoc_handler.py | 20 分钟 |
| 用例 | `_build_adhoc_collection()` | report_server.py | ✅ 稳定 | handlers/adhoc_handler.py | 25 分钟 |
| 用例 | `_append_manual_cases_to_collection()` | report_server.py | ✅ 稳定 | handlers/manual_case_handler.py | 30 分钟 |
| 用例 | `_remove_excluded_items()` | report_server.py | ✅ 稳定 | utils/collection_utils.py | 20 分钟 |

**统计**：2-3 个新模块，共 95 分钟

### 优先级 P3：Collection 遍历与查询（需要细心）

| 类别 | 函数 | 位置 | 签名稳定性 | 目标位置 | 预计工作量 |
|------|------|------|----------|---------|-----------|
| 查询 | `_item_by_path()` / `_find_item_fallback()` | report_server.py | ✅ 稳定 | utils/collection_utils.py | 30 分钟 |
| 查询 | `_iter_request_items()` | report_server.py | ✅ 稳定 | utils/collection_utils.py | 20 分钟 |
| 查询 | `_prune_collection_to_paths()` | report_server.py | ✅ 稳定 | utils/collection_utils.py | 25 分钟 |

**统计**：补充 utils/collection_utils.py，共 75 分钟

### 优先级 P4：已整合的 Helper 函数（需要重构边界）

| 类别 | 函数 | 位置 | 状态 | 目标位置 | 预计工作量 |
|------|------|------|------|---------|-----------|
| Job | `_execute_http_request()` | report_server.py | ✅ P1 | handlers/http_handler.py | 30 分钟 |
| Job | `_enqueue_job_with_worker()` | report_server.py | ✅ P1 | handlers/job_handler.py | 25 分钟 |
| Job | `_enqueue_retry_job()` | report_server.py | ✅ P1 | handlers/job_handler.py | 20 分钟 |

**统计**：2 个新 handler 模块，共 75 分钟

---

## 七、拆分前置验证清单

**在开始任何拆分前，必须验证以下项目**：

- [ ] 所有 50+ 个私有 helper 函数已编目
- [ ] 每个函数的依赖关系（其他函数、全局变量、配置、文件 I/O）已明确
- [ ] 每个函数的调用点已统计（出现次数）
- [ ] 已确认没有隐式全局状态依赖（如线程本地变量）
- [ ] 已确认 Flask request 上下文的依赖限制在路由层
- [ ] 已确认 IO 操作的限制（磁盘读写、网络请求）
- [ ] run_postman_tests() 的签名与行为已锁定（不可改变）
- [ ] PostmanTestReport 类的对外接口已锁定
- [ ] 所有 @app.route 的 HTTP 契约已锁定（输入/输出格式）

---

## 八、推荐拆分顺序

**建议按以下顺序执行（与计划阶段对应）**：

1. **P1 → 阶段 1**：抽离最稳定的纯函数
   - URL 处理 → utils/url_utils.py
   - 请求构建 → utils/request_builder.py
   - 响应解析 → utils/response_parser.py
   - 报告计算 → utils/report_utils.py
   
2. **P2 → 阶段 2 下半部分**：Collection 与用例处理
   - Ad-hoc 用例 → handlers/adhoc_handler.py
   - 手工用例 → handlers/manual_case_handler.py
   - 集合操作 → utils/collection_utils.py

3. **P3 → 阶段 3 下半部分**：Collection 查询与遍历

4. **P4 → 后续**：HTTP 与 Job 管理（已有 helper 可直接使用）

---

## 九、风险识别与缓解

| 风险 | 概率 | 缓解措施 |
|------|------|---------|
| 拆分后行为改变 | 中 | 每次拆分后完整 smoke 测试 |
| 隐式全局状态被遗漏 | 中 | 用 grep 搜索 global/nonlocal 声明 |
| Flask request 上下文逸出 | 低 | utils/ 中禁止导入 Flask，只接收参数 |
| 循环依赖 | 低 | 先收集所有依赖关系，画出依赖图 |
| 签名改变导致兼容性破裂 | 中 | 冻结所有对外公开入口的签名 |

---

## 十、实施与验证门禁

**阶段 0 完成条件**：
- [ ] 本清单文档已完成并经过审查
- [ ] 所有函数已分类（P1/P2/P3/P4）
- [ ] 所有依赖关系已明确（可用 .md 表格呈现）
- [ ] 目标文件结构已规划（handlers/, utils/ 的文件列表）
- [ ] 前置验证清单已逐项检查

**进入阶段 1 前**：
- [ ] 编译测试：report_server.py 无语法错误
- [ ] 冒烟测试：11 个关键端点返回 200/400
- [ ] 代码审查：确认无遗漏的拆分项

---

**下一步**：用户确认本清单内容 → 进入阶段 1（抽离 P1 纯函数）
