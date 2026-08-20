# assert_text_exists 增强修复总结

## 版本
v1.33.24 (2026-08-20)

## 用户反馈问题

### 报告 af835c863a1a 第9步断言失败
- **问题1**：断言失败没有截图
- **问题2**：iframe 内文本无法查找
- **问题3**：错误信息缺少诊断内容

### 问题分析
通过检查报告 `uireports/exec_af835c863a1a/result.json` 发现：
- 第9步（index=8）查找文本 "`合作商名称`"（带反引号）
- 实际页面文本是"合作商名称"（没有反引号）
- 旧版代码只查主框架，不查 iframe
- 失败时没有截图
- 错误信息只显示前200字，缺少完整诊断

## 修复内容

### 1. iframe 支持
**修改文件**：
- `postman_api_tester/services/ui_headless_engine.py`
- `postman_api_tester/services/ui_recorder_inject.py`

**实现**：
- 新增 `_count_text_in_all_frames()` 方法
- 遍历主框架和所有 iframe（page.frames）查找文本
- 跨域 iframe 自动跳过（捕获异常）

**验证**：
```python
# 集成测试结果
测试 2：查找 iframe 文本 '供应商名称'
  状态：passed
  匹配数：1
  [PASS] 通过
```

### 2. 截图功能
**修改文件**：
- `postman_api_tester/services/ui_recorder_inject.py`

**实现**：
- 断言失败时调用 `_captureScreenshot()`
- 截图保存到 `uireports/exec_{job_id}/screenshots/step_{index}_fail.png`

**验证**：
- 无头引擎：外层循环已有截图逻辑（line 713）
- 浏览器回放：新增截图调用（line 1888-1893）

### 3. 错误信息增强
**修改文件**：
- `postman_api_tester/services/ui_headless_engine.py`
- `postman_api_tester/services/ui_recorder_inject.py`

**新增内容**：
- 页面文本预览（前500字 + 总字数）
- frame 数量统计
- 当前 URL
- 匹配数量（match_count）

**示例**：
```
断言失败: 页面未找到文本 '供应商名称'；
页面文本预览: '订单管理 合作商名称 金额 202608200001 测试供应商A 100.00' (共 85 字)；
已扫描 2 个 frame；
当前 URL: http://example.com/order
```

### 4. 匹配数量返回
**修改文件**：
- `postman_api_tester/services/ui_headless_engine.py`
- `postman_api_tester/services/ui_recorder_inject.py`

**实现**：
- 成功时返回 `match_count` 字段
- 显示文本在页面中出现的次数

**示例**：
```json
{
  "status": "passed",
  "match_count": 3,
  "value": "供应商"
}
```

## 测试验证

### 单元测试
```bash
$ python -m pytest tests/test_assert_text_exists.py -v
8 passed in 5.61s
```

### 集成测试
```bash
$ python test_iframe_assertion.py
✓ 创建测试文件
✓ 页面已加载

测试 1：查找主框架文本 '主框架标题'
  状态：passed
  匹配数：1
  ✓ 通过

测试 2：查找 iframe 文本 '供应商名称'
  状态：passed
  匹配数：1
  ✓ 通过

测试 3：查找不存在的文本
  状态：failed
  错误信息包含完整诊断内容
  ✓ 通过

✓ 所有测试通过！
```

### 全量测试
```bash
$ python -m pytest tests/ -q
2198 passed in 14.21s
```

### 类型检查
```bash
$ python -m mypy postman_api_tester
Success: no issues found in 97 source files
```

## 用户场景验证

### 报告 af835c863a1a 第9步
**原因分析**：
- 用户输入时多打了反引号："`合作商名称`"
- 页面实际文本是："合作商名称"
- 不是代码问题，是输入问题

**验证结果**：
```
测试 1：查找 '合作商名称'（正确输入）
  状态：passed
  匹配数：1
  ✓ 成功找到文本

测试 2：查找 '`合作商名称`'（错误输入）
  状态：failed
  ✓ 预期失败（页面没有反引号）
  错误信息包含完整诊断内容
```

## 使用建议

### 正确用法
```javascript
// 查找"合作商名称"
{
  "action": "assert_text_exists",
  "value": "合作商名称"
}
```

### 错误示例
```javascript
// 不要带多余的引号
{
  "action": "assert_text_exists",
  "value": "`合作商名称`"  // 错误：页面没有反引号
}
```

### iframe 场景
现在自动支持 iframe，无需额外配置：
```javascript
// 会自动查找主框架和所有 iframe
{
  "action": "assert_text_exists",
  "value": "供应商名称"
}
```

## 回退方案
如需回退，可以执行：
```bash
git revert 51edd12
```

## 相关文件
- `postman_api_tester/services/ui_headless_engine.py` - 无头引擎实现
- `postman_api_tester/services/ui_recorder_inject.py` - 浏览器回放实现
- `tests/test_assert_text_exists.py` - 单元测试
- `test_iframe_assertion.py` - 集成测试（已删除）
- `test_user_scenario.py` - 用户场景测试（已删除）

## 总结
本次修复解决了用户反馈的三个问题：
1. ✓ 断言失败现在有截图
2. ✓ iframe 内文本可以查找
3. ✓ 错误信息包含完整诊断内容

同时增强了功能：
- 返回匹配数量
- 自动遍历所有 frame
- 更详细的错误提示

所有测试通过，可以放心使用。
