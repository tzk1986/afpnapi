---
name: handler-service-param-sync
description: 多层调用链中修改函数签名时，必须同步更新所有层级的参数透传
metadata:
  type: feedback
---

## 规则

修改函数签名（新增/删除/重命名参数）时，必须检查并同步更新整个调用链上所有层级的函数，包括中间转发层。

**Why:** Python 的 keyword argument 传递在运行时才会检查参数匹配。如果中间转发层（如 handler）没有同步更新参数，编译期不会报错，但运行时会抛出 `TypeError: got an unexpected keyword argument`。这类问题难以通过静态分析发现，只有在实际执行路径被触发时才会暴露。

**How to apply:**
1. 修改函数签名前，先 grep 查找所有调用点
2. 区分"最终实现层"和"中间转发层"（handler → service → executor 是常见模式）
3. 每层都要同步更新参数定义和透传调用
4. 对于 `partial()` 包装的对象，要检查包装时是否固定了某些参数
5. 修改后用实际调用路径做冒烟测试，不能只检查函数签名

## 本次案例

**修改内容：** `run_postman_job()` 新增 `judgment_config` 参数

**出错位置：** `postman_api_tester/handlers/job_handler.py:run_postman_job()`

**原因：**
- 只更新了 `services/report_job_execution_service.py` 中的实现
- 漏更新了 `handlers/job_handler.py` 中的转发函数
- 实际调用链：`job_routes.py` → `job_handler.py` → `report_job_execution_service.py`
- `job_handler.py` 是中间转发层，只负责日志和依赖注入，容易遗漏

**修复方式：** 在 `job_handler.py:run_postman_job()` 的签名和转发调用中都添加 `judgment_config` 参数

## 检查清单

新增/修改函数参数时的检查清单：

- [ ] `grep` 查找所有同名函数定义（可能有多个重载或转发）
- [ ] 检查 `partial()` 包装是否固定了参数
- [ ] 检查中间转发层是否同步更新
- [ ] 检查调用方（caller）是否传递了新参数
- [ ] 冒烟测试覆盖实际执行路径
