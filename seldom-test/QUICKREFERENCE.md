# 📄 Seldom 版本快速参考卡

打印或保存本卡片，快速查阅必要信息

---

## 🚀 30秒快速开始

```bash
# 1. 进入目录
cd seldom-test

# 2. 安装依赖
pip install -r requirements.txt

# 3. 运行演示
python demo_seldom_tester.py

# 4. 查看报告
# 打开生成的 HTML 文件
```

---

## 📝 命令速查

| 命令 | 用途 | 示例 |
|------|------|------|
| 演示 | 查看功能演示 | `python demo_seldom_tester.py` |
| 运行测试 | 执行 Postman 文件 | `python practical_seldom_tester.py file.json` |
| 自定义 URL | 指定基础 URL | `python practical_seldom_tester.py file.json https://api.com` |
| 自定义输出 | 指定报告目录 | `python practical_seldom_tester.py file.json https://api.com ./reports` |
| 单元测试 | 验证功能 | `python test_seldom_postman.py` |
| 查看示例 | 代码示例 | `python seldom_examples.py` |

---

## 📚 文档速查表

| 需求 | 查看文档 | 阅读时间 |
|------|---------|---------|
| 快速开始 | [QUICKSTART.md](QUICKSTART.md) | 5-10 分钟 |
| 功能说明 | [README.md](README.md) | 5-15 分钟 |
| 项目结构 | [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) | 20-30 分钟 |
| 技术方案 | [IMPLEMENTATION.md](IMPLEMENTATION.md) | 30-50 分钟 |
| 文档导航 | [INDEX.md](INDEX.md) | 10-15 分钟 |
| 本内容 | [QUICKREFERENCE.md](QUICKREFERENCE.md) | 2-5 分钟 |

---

## 🎯 文件说明

| 文件 | 用途 | 推荐 |
|------|------|------|
| practical_seldom_tester.py | 主程序 | ⭐⭐⭐ |
| demo_seldom_tester.py | 演示脚本 | ⭐⭐ |
| simple_seldom_tester.py | 简化版本 | ⭐ |
| seldom_postman_tester.py | 复杂版本 | ⭐ |
| test_seldom_postman.py | 单元测试 | ⭐ |
| seldom_examples.py | 代码示例 | ⭐ |

---

## 🔧 配置要点

### 安装依赖
```bash
pip install -r requirements.txt
# 自动安装 seldom 和 requests
```

### 修改基础 URL
**方式 1**: 命令行
```bash
python practical_seldom_tester.py file.json https://staging.api.com
```

**方式 2**: 代码中
```python
run_seldom_postman_tests(file, base_url='https://custom.com')
```

### 修改输出目录
```bash
python practical_seldom_tester.py file.json url ./my_reports
```

---

## ❓ 常见问题速查

| 问题 | 答案 | 详见 |
|------|------|------|
| 如何安装? | `pip install -r requirements.txt` | QUICKSTART |
| 如何运行? | `python demo_seldom_tester.py` | QUICKSTART |
| 支持什么方法? | GET/POST/PUT/DELETE/PATCH | README |
| 属性冲突怎么办? | 使用 api_response/api_status_code | IMPLEMENTATION |
| 如何自定义? | 阅读 IMPLEMENTATION 的扩展指南 | IMPLEMENTATION |
| 报告存哪儿? | ../reports 目录（默认） | QUICKSTART |
| 如何调试? | 查看控制台输出和 HTML 报告 | QUICKSTART |

---

## 🎓 关键概念

### 属性冲突问题
**问题**: Seldom 的 response/status_code 是只读的
**解决**: 使用 api_response/api_status_code 替代

### 动态测试类
**原理**: 用 type() 函数动态生成测试类
**好处**: 每个 API 一个独立类，高度灵活

### JSON 递归解析
**方式**: 递归处理文件夹和请求
**结果**: 自动识别结构，提取所有 API

### 支持的 URL 格式
- 相对 URL: `/users` → `https://api.com/users`
- 完整 URL: `https://api.com/users` → 直接使用
- 带参数: `/users?id=1` → 自动处理

---

## 📊 项目统计

- 📁 核心文件: 4 个 Python 文件
- 📚 文档文件: 6 个 Markdown 文件
- 📝 代码行数: ~1200 行
- 📖 文档行数: ~1250+ 行
- ⚙️ 支持方法: GET/POST/PUT/DELETE/PATCH
- 🌍 支持 URL: 相对/完整/带参数

---

## 💡 最佳实践

1. ✅ 先用演示程序了解功能
2. ✅ 用自己的 Postman 文件测试
3. ✅ 定期查看 HTML 报告
4. ✅ 将报告集成到 CI/CD
5. ✅ 保留 JSON 配置文件备查

---

## 🔗 链接便捷导航

**本目录下的所有文件**:
- [README.md](README.md) - 功能说明
- [QUICKSTART.md](QUICKSTART.md) - 快速入门
- [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) - 项目结构
- [IMPLEMENTATION.md](IMPLEMENTATION.md) - 实现方案
- [INDEX.md](INDEX.md) - 文档导航
- [DOCUMENTATION.md](DOCUMENTATION.md) - 文档统计

**Python 文件**:
- [practical_seldom_tester.py](practical_seldom_tester.py) - 主程序
- [test_seldom_postman.py](test_seldom_postman.py) - 单元测试
- [demo_seldom_tester.py](demo_seldom_tester.py) - 演示脚本

---

## 📞 技术支持查询

### 问题类型 → 查阅位置

| 问题 | 位置 |
|------|------|
| 安装问题 | QUICKSTART - 安装 |
| 运行问题 | QUICKSTART - 快速开始 |
| 功能问题 | README - 使用方法 |
| 配置问题 | QUICKSTART - 配置 |
| 错误问题 | QUICKSTART - 常见问题 |
| 结构问题 | PROJECT_STRUCTURE |
| 设计问题 | IMPLEMENTATION |
| 导航问题 | INDEX |

---

## ⏱️ 时间规划

### 0-5 分钟
- [ ] 运行 `python demo_seldom_tester.py`
- [ ] 查看生成的 HTML 报告

### 5-15 分钟
- [ ] 读 QUICKSTART.md 的快速开始部分
- [ ] 理解三种使用方式

### 15-30 分钟
- [ ] 用自己的 Postman 文件测试一次
- [ ] 观察控制台输出和 HTML 报告

### 30+ 分钟
- [ ] 阅读 README.md 了解完整功能
- [ ] 阅读 PROJECT_STRUCTURE.md 理解结构
- [ ] 阅读 IMPLEMENTATION.md 学习设计

---

## 🎁 一页纸总结

seldom-test 是一个基于 Seldom 框架的 Postman API 测试工具。

**核心分层**:
- 测试执行层 - 主入口 run_seldom_postman_tests()
- 业务逻辑层 - 解析器和测试类创建
- 基础设施层 - Seldom HTTP 方法和报告生成

**关键特点**:
- ✅ 解决了 Seldom 的属性冲突问题
- ✅ 支持动态测试类生成
- ✅ 完整的报告生成（HTML+控制台）
- ✅ 支持自定义 Base URL
- ✅ 支持所有常用 HTTP 方法

**快速开始**:
```bash
python demo_seldom_tester.py  # 看演示
python practical_seldom_tester.py your_file.json  # 运行测试
```

**更多信息**: 查看 QUICKSTART.md

---

## ✨ 记住这 6 个词

1. **解析** - 解析 Postman JSON 文件
2. **动态** - 动态创建测试类
3. **执行** - 执行 HTTP 请求
4. **验证** - 验证响应状态码
5. **收集** - 收集测试结果
6. **报告** - 生成 HTML 和控制台报告

---

**打印此卡片并保存于手边，快速查阅时非常有用！**

---

**最后更新**: 2026-04-08  
**版本**: 1.0  
**作者**: seldom-test 项目