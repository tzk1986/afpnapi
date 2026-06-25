# Pre-request 脚本实现方案

## Context

当前系统已具备完整的变量替换体系：
- 6 个内置函数（timestamp/uuid/random_int/date/datetime/timestamp_ms）
- `{{variable}}` 和 `{{func(args)}}` 两种占位符
- `VariableContext` 跨接口传递提取的变量
- `x_extract` 从响应中提取变量

**用户需求**：实现类似 Postman Pre-request Script 的能力，在请求发出前动态计算变量值。

**两步走策略**：
- **Step A**：扩展内置变量函数（低风险，覆盖 80% 常见场景）
- **Step B**：新增 `x_pre_request` 字段，支持 Python 表达式（中等风险，需沙箱）

---

## 代码走查结果

### 现有架构（关键文件）

| 文件 | 职责 | 关键接口 |
|------|------|---------|
| `utils/variable_functions.py` | 内置函数注册与调用 | `@register(name)`、`evaluate_function()`、`get_function_metadata()` |
| `utils/variable_substitution.py` | 变量替换引擎 | `substitute_variables()`、`substitute_in_api_config()` |
| `core/variable_context.py` | 变量上下文管理 | `VariableContext.get/set/update_from_extract()` |
| `parser.py` | 集合解析 | `ApiConfig` TypedDict（已有 x_* 扩展字段模式） |
| `executor.py:307-309` | 执行前变量替换 | `substitute_in_api_config(api, self.variable_context.variables)` |
| `config.py` | 配置开关 | `ENABLE_VARIABLE_FUNCTIONS` 等 |
| `templates/collection_editor.html` | 前端编辑器 | tabs: general/headers/params/body/extract |

### 变量替换调用链

```
executor.execute_test()
  ↓ (line 307-309)
substitute_in_api_config(api, variable_context.variables)
  ↓
substitute_variables(text, variables)
  ↓ (第一轮：函数调用)
_FUNC_PATTERN.sub(_func_replacer, text)
  ↓
evaluate_function(name, args_str)
  ↓
_BUILT_IN_FUNCTIONS[name](*args)
  ↓ (第二轮：普通变量)
_VARIABLE_PATTERN.sub(_var_replacer, text)
```

### 扩展点分析

1. **内置函数注册**：`@register(name)` 装饰器，注册即生效，无额外配置
2. **函数元数据**：`_FUNCTION_META` 字典，用于 UI 帮助面板展示
3. **ApiConfig 扩展**：已有 `x_extract`/`x_success_err_codes` 等 x_* 字段模式，新增 `x_pre_request` 遵循相同模式
4. **配置开关**：`ENABLE_VARIABLE_FUNCTIONS` 已存在，Step B 可新增 `ENABLE_PRE_REQUEST_SCRIPT`

---

## Step A：扩展内置变量函数

### 目标

新增 6 个常用函数，覆盖签名、编码、随机值场景：

| 函数名 | 语法 | 功能 | 示例 |
|--------|------|------|------|
| `hmac_sha256` | `{{hmac_sha256(data,key)}}` | HMAC-SHA256 签名 | `{{hmac_sha256(order123,secret)}}` → `a3f5...` |
| `md5` | `{{md5(text)}}` | MD5 哈希 | `{{md5(password)}}` → `5f4d...` |
| `base64_encode` | `{{base64_encode(text)}}` | Base64 编码 | `{{base64_encode(user:pass)}}` → `dXNlcjpwYXNz` |
| `base64_decode` | `{{base64_decode(text)}}` | Base64 解码 | `{{base64_decode(dXNlcjpwYXNz)}}` → `user:pass` |
| `random_string` | `{{random_string(length,charset)}}` | 随机字符串 | `{{random_string(16,alpha)}}` → `abcXYZ...` |
| `url_encode` | `{{url_encode(text)}}` | URL 编码 | `{{url_encode(hello world)}}` → `hello%20world` |

### 实现细节

**文件**：`utils/variable_functions.py`

```python
import hashlib
import hmac
import base64
import string
from urllib.parse import quote

@register("hmac_sha256")
def _hmac_sha256(data: str = "", key: str = "") -> str:
    """HMAC-SHA256 签名，返回十六进制字符串。"""
    if not data or not key:
        return ""
    return hmac.new(key.encode("utf-8"), data.encode("utf-8"), hashlib.sha256).hexdigest()

@register("md5")
def _md5(text: str = "") -> str:
    """MD5 哈希，返回十六进制字符串。"""
    if not text:
        return ""
    return hashlib.md5(text.encode("utf-8")).hexdigest()

@register("base64_encode")
def _base64_encode(text: str = "") -> str:
    """Base64 编码。"""
    if not text:
        return ""
    return base64.b64encode(text.encode("utf-8")).decode("utf-8")

@register("base64_decode")
def _base64_decode(text: str = "") -> str:
    """Base64 解码。"""
    if not text:
        return ""
    try:
        return base64.b64decode(text.encode("utf-8")).decode("utf-8")
    except Exception:
        return ""

@register("random_string")
def _random_string(length: str = "8", charset: str = "alphanumeric") -> str:
    """随机字符串。charset 可选：alpha/alphanumeric/numeric/hex。"""
    charset_map = {
        "alpha": string.ascii_letters,
        "alphanumeric": string.ascii_letters + string.digits,
        "numeric": string.digits,
        "hex": string.hexdigits[:16],
    }
    chars = charset_map.get(charset, charset_map["alphanumeric"])
    return "".join(random.choice(chars) for _ in range(int(length)))

@register("url_encode")
def _url_encode(text: str = "") -> str:
    """URL 编码。"""
    if not text:
        return ""
    return quote(text, safe="")
```

**同步更新 `_FUNCTION_META`**，为每个新函数添加 UI 帮助信息。

### 测试

新增 `tests/test_variable_functions_extended.py`：
- 每个函数的正常路径（典型输入）
- 边界情况（空字符串、特殊字符、超长输入）
- 参数错误（缺失参数、无效 charset）

---

## Step B：x_pre_request Python 表达式字段

### 目标

允许用户在每个 API 配置中定义 Python 表达式，在请求发出前执行，动态设置变量。

**语法设计**：
```json
{
  "request": {
    "method": "POST",
    "url": "/api/orders",
    "x_pre_request": {
      "timestamp": "int(time.time())",
      "sign": "hmac.new('secret'.encode(), '{{timestamp}}'.encode(), hashlib.sha256).hexdigest()"
    }
  }
}
```

**执行时机**：在 `substitute_in_api_config()` 之前，先执行 `x_pre_request` 表达式，将结果写入 `variable_context`，然后正常变量替换流程即可引用这些变量。

### 安全沙箱设计

**风险**：任意 Python 代码执行可能导致安全问题（文件操作、系统调用、网络访问）。

**沙箱策略**：
1. **限制内置函数**：`__builtins__` 设为空字典，禁用 `open`/`exec`/`eval`/`import` 等
2. **白名单模块**：仅允许 `hashlib`、`hmac`、`base64`、`time`、`json`、`re`
3. **禁止危险操作**：正则检查 `import`/`__import__`/`os`/`sys`/`subprocess` 等关键字
4. **超时保护**：表达式执行超时 1 秒，超时则跳过并记录警告
5. **配置开关**：`ENABLE_PRE_REQUEST_SCRIPT = false` 默认关闭

### 实现细节

**1. 配置开关**（`config.py`）：
```python
ENABLE_PRE_REQUEST_SCRIPT = str(os.environ.get("ENABLE_PRE_REQUEST_SCRIPT", "false")).strip().lower() in {
    "1", "true", "yes", "y", "on"
}
```

**2. 沙箱执行器**（新建 `utils/pre_request_executor.py`）：
```python
import hashlib
import hmac
import base64
import time
import json
import re
import signal
from typing import Dict, Optional

_SAFE_BUILTINS = {
    "int": int, "str": str, "float": float, "bool": bool,
    "len": len, "range": range, "list": list, "dict": dict,
    "True": True, "False": False, "None": None,
}

_SAFE_MODULES = {
    "hashlib": hashlib, "hmac": hmac, "base64": base64,
    "time": time, "json": json, "re": re,
}

_DANGEROUS_KEYWORDS = re.compile(
    r"\b(import|__import__|exec|eval|compile|open|os|sys|subprocess|__builtins__|globals|locals)\b"
)

class PreRequestTimeout(Exception):
    pass

def _timeout_handler(signum, frame):
    raise PreRequestTimeout("pre-request expression timeout")

def execute_pre_request(
    expressions: Dict[str, str],
    existing_variables: Dict[str, str],
) -> Dict[str, str]:
    """执行 pre-request 表达式，返回结果变量字典。
    
    - expressions: {变量名: Python 表达式}
    - existing_variables: 当前已有的变量（可在表达式中引用）
    """
    if not expressions:
        return {}
    
    result: Dict[str, str] = {}
    sandbox_globals = {"__builtins__": _SAFE_BUILTINS}
    sandbox_globals.update(_SAFE_MODULES)
    sandbox_globals.update({"variables": existing_variables, "result": result})
    
    for var_name, expression in expressions.items():
        if _DANGEROUS_KEYWORDS.search(expression):
            result[var_name] = ""
            continue
        
        old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(1)
        try:
            value = eval(expression, sandbox_globals)
            result[var_name] = str(value) if value is not None else ""
        except Exception:
            result[var_name] = ""
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)
    
    return result
```

**注意**：`signal.SIGALRM` 仅在 Unix 可用，Windows 需改用 `threading.Timer` 或 `concurrent.futures` 超时机制。

**3. 解析器扩展**（`parser.py`）：

在 `_parse_request()` 中添加：
```python
x_pre_request_raw = request.get("x_pre_request")
x_pre_request: Optional[Dict[str, str]] = None
if isinstance(x_pre_request_raw, dict) and x_pre_request_raw:
    x_pre_request = {str(k): str(v) for k, v in x_pre_request_raw.items() if isinstance(v, str)}
    if not x_pre_request:
        x_pre_request = None
```

在 `ApiConfig` TypedDict 中添加：
```python
x_pre_request: Optional[Dict[str, str]]
```

**4. 执行流程集成**（`executor.py`）：

在 `execute_test()` 中，变量替换前执行：
```python
if self.variable_context is not None:
    # 先执行 pre-request 表达式
    pre_request_expr = api.get("x_pre_request")
    if pre_request_expr and _is_pre_request_enabled():
        from postman_api_tester.utils.pre_request_executor import execute_pre_request
        pre_vars = execute_pre_request(pre_request_expr, self.variable_context.variables)
        for k, v in pre_vars.items():
            self.variable_context.set(k, v)
    
    # 再进行常规变量替换
    from postman_api_tester.utils.variable_substitution import substitute_in_api_config
    api = substitute_in_api_config(api, self.variable_context.variables)
    self.api_config = dict(api)
```

**5. 前端 UI**（`templates/collection_editor.html`）：

在 tabs 中新增 `pre_request` 标签：
```javascript
const tabs = ['general', 'headers', 'params', 'body', 'pre_request', 'extract'];
const tabLabels = {
    general: 'General', headers: 'Headers', params: 'Params',
    body: 'Body', pre_request: 'Pre-request', extract: 'x_extract'
};
```

新增 `renderPreRequestTab()` 函数，渲染键值对编辑器（类似 x_extract 的 UI），允许用户添加/删除表达式。

### 测试

1. **单元测试**：
   - 沙箱执行器：正常表达式、危险表达式、超时表达式、语法错误
   - 解析器：`x_pre_request` 字段解析
   - 执行器：变量替换前的 pre-request 执行

2. **集成测试**：
   - 完整流程：配置 `x_pre_request` → 执行 → 验证变量被正确设置和引用

---

## 风险分析与缓解

### Step A 风险

| 风险 | 级别 | 缓解措施 |
|------|------|---------|
| 新函数参数解析错误 | 低 | `evaluate_function()` 已有 try-except 捕获 TypeError/ValueError，返回空字符串 |
| 性能影响 | 低 | 哈希/编码操作为 CPU 密集型，单次调用 < 1ms，无显著影响 |
| 兼容性 | 低 | 仅新增函数，不修改现有逻辑，向后兼容 |

### Step B 风险

| 风险 | 级别 | 缓解措施 |
|------|------|---------|
| 代码注入 | 高 | 沙箱 + 关键字检查 + 白名单模块 |
| 拒绝服务（死循环） | 中 | 1 秒超时保护 |
| 跨平台兼容 | 中 | `signal.SIGALRM` 仅 Unix 可用，Windows 需 `threading.Timer`（见下方详细方案） |
| 调试困难 | 中 | 表达式执行失败返回空字符串，日志记录详细错误 |
| 安全风险 | 高 | 默认关闭（`ENABLE_PRE_REQUEST_SCRIPT=false`），需显式启用 |
| **并发竞争** | **高** | 同批次并发 API 的 pre-request 变量可能互相覆盖（见下方详细方案） |
| **变量覆盖冲突** | 中 | pre-request 设置的变量与已有变量同名时的处理策略 |
| **批次调度集成** | 中 | pre-request 设置变量的 API 需要被批次调度器识别为生产者 |

---

## 代码走查补充发现

### 发现 1：并发执行竞争风险

**问题描述**：
- `VariableContext.variables` 属性返回**字典副本**（`core/variable_context.py:35-36`）
- 并发模式下（`ENABLE_CONCURRENT=true`），同批次多个 API 同时执行 pre-request
- 如果 API-A 的 pre-request 设置 `sign=abc`，API-B 的 pre-request 设置 `sign=xyz`，两者同时执行会导致竞争

**缓解方案**：
```python
# 方案 A：pre-request 设置变量时使用 API 名称作为前缀（推荐）
# 避免不同 API 的变量互相覆盖
result[f"{api_name}.{var_name}"] = str(value)

# 方案 B：pre-request 变量仅在单次请求内有效，不写入全局 context
# 使用局部变量字典，传给 substitute_variables() 合并
local_vars = execute_pre_request(expr, existing_vars)
merged_vars = {**existing_vars, **local_vars}
api = substitute_in_api_config(api, merged_vars)  # 不写入 context
```

**推荐**：采用方案 B，pre-request 变量仅在当前请求的变量替换中使用，不污染全局 context。这与 Postman 的行为一致（pre-request 脚本变量仅在单次请求内有效）。

### 发现 2：Windows 超时方案

**问题描述**：
`signal.SIGALRM` 仅在 Unix 系统可用，Windows 不支持。

**跨平台方案**：
```python
import sys
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

def execute_pre_request(expressions, existing_variables, timeout_seconds=1):
    """跨平台的 pre-request 执行器。"""
    if sys.platform == "win32":
        # Windows: 使用 ThreadPoolExecutor + future.result(timeout)
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_execute_expressions, expressions, existing_variables)
            try:
                return future.result(timeout=timeout_seconds)
            except FuturesTimeout:
                logger.warning("pre-request expression timeout (%ds)", timeout_seconds)
                return {k: "" for k in expressions}
    else:
        # Unix: 使用 signal.SIGALRM（更高效）
        return _execute_with_signal_timeout(expressions, existing_variables, timeout_seconds)
```

### 发现 3：批次调度器集成

**问题描述**：
`core/batch_scheduler.py` 根据 `x_extract`（生产者）和 `{{variable}}`（消费者）计算依赖关系，决定分批策略。如果 API-A 的 pre-request 设置了变量 `sign`，而 API-B 的 URL 中引用了 `{{sign}}`，批次调度器需要识别这种依赖。

**缓解方案**：
1. **简单方案**：pre-request 设置的变量**不参与批次调度**，仅在同一 API 内使用
2. **完整方案**：解析 pre-request 表达式的输出变量名，加入批次调度器的依赖图

**推荐**：采用简单方案，pre-request 变量视为"局部变量"，不影响批次调度。如果用户需要跨 API 传递变量，应使用 `x_extract`。

### 发现 4：执行流程集成点

**当前流程**（`executor.py:307-309`）：
```python
if self.variable_context is not None:
    api = substitute_in_api_config(api, self.variable_context.variables)
    self.api_config = dict(api)
```

**改造后流程**：
```python
if self.variable_context is not None:
    # Step 1: 执行 pre-request 表达式（局部变量）
    pre_request_expr = api.get("x_pre_request")
    local_vars = {}
    if pre_request_expr and _is_pre_request_enabled():
        from postman_api_tester.utils.pre_request_executor import execute_pre_request
        local_vars = execute_pre_request(pre_request_expr, self.variable_context.variables)
        # 记录日志：成功设置了哪些变量
        if local_vars:
            logger.debug("pre-request variables set: %s", list(local_vars.keys()))
    
    # Step 2: 合并局部变量到全局变量（仅用于本次替换）
    merged_vars = {**self.variable_context.variables, **local_vars}
    
    # Step 3: 变量替换
    api = substitute_in_api_config(api, merged_vars)
    self.api_config = dict(api)
```

### 发现 5：错误处理与日志

**改进点**：
1. 表达式执行失败时，应记录**具体错误信息**（而非仅返回空字符串）
2. 危险表达式被拦截时，应记录警告日志
3. 超时发生时，应记录哪个表达式超时

**日志示例**：
```python
try:
    value = eval(expression, sandbox_globals)
    result[var_name] = str(value) if value is not None else ""
except SyntaxError as e:
    logger.warning("pre-request syntax error in '%s': %s", var_name, e)
    result[var_name] = ""
except Exception as e:
    logger.warning("pre-request execution error in '%s': %s", var_name, type(e).__name__)
    result[var_name] = ""
```

---

## 优化后的安全边界

**信任模型**：
- 上传的 Postman 集合文件视为**可信来源**（与现有 x_extract 一致）
- 若需支持不可信集合，必须启用沙箱 + 严格审查

**SSRF 防护**：
- Pre-request 表达式**不允许发起网络请求**（不在白名单模块中）
- 与现有 `PROXY_ALLOWED_HOSTS` 机制无冲突

**数据泄露防护**：
- 沙箱禁用 `open`/`os`/`sys`，无法读取文件或环境变量
- 仅允许纯计算操作（哈希、编码、时间戳等）

**变量隔离**：
- pre-request 变量仅在单次请求内有效（局部变量）
- 不写入全局 VariableContext，避免并发竞争
- 不影响批次调度器的依赖计算

---

## 实施步骤

### Phase 1：Step A（1-2 天）

1. **实现新函数**（`utils/variable_functions.py`）
   - 添加 6 个新函数（hmac_sha256/md5/base64_encode/base64_decode/random_string/url_encode）
   - 更新 `_FUNCTION_META`

2. **编写测试**（`tests/test_variable_functions_extended.py`）
   - 每个函数的正常/边界/错误路径
   - 目标覆盖率 > 90%

3. **验证**
   - pytest 全通过
   - mypy 通过
   - 手动验证：在集合中使用 `{{md5(test)}}` 等函数，确认替换正确

### Phase 2：Step B（3-5 天）

1. **配置开关**（`config.py`）
   - 添加 `ENABLE_PRE_REQUEST_SCRIPT`，默认 false

2. **沙箱执行器**（`utils/pre_request_executor.py`）
   - 实现 `execute_pre_request()` 函数
   - 处理跨平台超时（Unix: SIGALRM, Windows: threading）

3. **解析器扩展**（`parser.py`）
   - `ApiConfig` 添加 `x_pre_request` 字段
   - `_parse_request()` 解析该字段

4. **执行流程集成**（`executor.py`）
   - 在变量替换前调用 `execute_pre_request()`
   - 将结果写入 `variable_context`

5. **前端 UI**（`templates/collection_editor.html`）
   - 新增 `pre_request` tab
   - 实现 `renderPreRequestTab()` 函数

6. **测试**
   - 沙箱执行器单元测试
   - 解析器/执行器集成测试
   - 端到端测试：配置表达式 → 执行 → 验证变量

7. **文档更新**
   - 操作手册：新增 Pre-request 脚本章节
   - 开发阅读文档：架构说明

---

## 验证清单

### Step A 验证
- [ ] 6 个新函数单元测试全部通过
- [ ] 在集合 JSON 中使用 `{{md5(test)}}` 等函数，请求中变量被正确替换
- [ ] 函数元数据在 UI 帮助面板中正确展示
- [ ] pytest 全量通过（1543+ tests）
- [ ] mypy 无新增错误

### Step B 验证
- [ ] 配置开关默认关闭时，`x_pre_request` 字段被忽略
- [ ] 启用后，表达式执行结果写入 `variable_context`
- [ ] 危险表达式（`import os`）被拦截，返回空字符串
- [ ] 超时表达式（`while True: pass`）1 秒后跳过
- [ ] 前端 UI 正确显示/编辑 `x_pre_request` 配置
- [ ] 端到端流程：配置签名表达式 → 执行请求 → 验证签名正确

---

## 关键文件清单

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `utils/variable_functions.py` | 修改 | 新增 6 个内置函数 + 元数据 |
| `utils/pre_request_executor.py` | **新建** | 沙箱执行器（Step B） |
| `config.py` | 修改 | 新增 `ENABLE_PRE_REQUEST_SCRIPT` 开关 |
| `parser.py` | 修改 | `ApiConfig` 添加 `x_pre_request` 字段 |
| `executor.py` | 修改 | 变量替换前调用 pre-request 执行 |
| `templates/collection_editor.html` | 修改 | 新增 Pre-request tab |
| `tests/test_variable_functions_extended.py` | **新建** | Step A 测试 |
| `tests/test_pre_request_executor.py` | **新建** | Step B 沙箱测试 |

---

## 附录：开放平台动态签名对比

参考 `2026-05-19-开放平台动态签名预处理方案.md` 中的设计，本方案的 Step A（内置函数扩展）可以覆盖大部分开放平台签名需求：

| 签名算法 | 本方案支持 | 说明 |
|---------|-----------|------|
| HMAC-SHA256 | ✅ | `{{hmac_sha256(data,key)}}` |
| MD5 | ✅ | `{{md5(text)}}` |
| Base64 编码 | ✅ | `{{base64_encode(text)}}` |
| URL 编码 | ✅ | `{{url_encode(text)}}` |
| 时间戳 | ✅ | `{{timestamp()}}`（已有） |
| 随机字符串 | ✅ | `{{random_string(len,charset)}}` |

对于更复杂的签名场景（如需要多步骤计算），则需要 Step B 的 `x_pre_request` 表达式支持。
