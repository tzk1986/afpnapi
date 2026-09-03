# 服务器部署检查清单

## 部署就绪度评估

### ✅ 已实现功能

#### 1. 接口测试 CLI
- **状态**: ✅ 完全可用
- **入口**: `python tools/scaffold/run_daily_smoke.py <manifest.txt>`
- **特点**:
  - 完全无头运行，不依赖 report server
  - 支持失败自动重试
  - 返回正确退出码（0=全过，1=有失败，2=参数错误）
  - 支持飞书推送
  - 生成 JSON + Markdown 汇总报告

#### 2. UI 测试 CLI
- **状态**: ✅ 完全可用
- **入口**: `python tools/scaffold/run_ui_tests.py [选项]`
- **特点**:
  - Playwright headless 模式，无需显示器
  - 支持批量执行、标签过滤、截图
  - 返回正确退出码
  - 支持飞书推送
  - 生成 JSON + Markdown 汇总报告

#### 3. 定时任务配置
- **Windows**: `tools/scaffold/setup_scheduled_tasks.ps1`
- **Linux/Mac**: `tools/scaffold/setup_cron_tasks.sh`
- **特点**: 一键配置，支持自定义执行时间

---

## 服务器部署步骤

### 前提条件

1. **Python 3.10+** 已安装
2. **网络访问**: 服务器可访问目标测试环境
3. **存储空间**: 至少 500MB（Playwright 浏览器约 300MB）

### 步骤 1: 部署代码

```bash
# 克隆代码到服务器
cd /opt  # 或你的部署目录
git clone <仓库地址> seldom-api-testing
cd seldom-api-testing
```

### 步骤 2: 安装依赖

```bash
# 安装 Python 依赖
pip install -r requirements.txt

# 安装 Playwright 及浏览器（UI 测试必需）
pip install playwright
playwright install chromium  # 或 firefox/webkit

# Linux 服务器可能需要安装系统依赖
# Ubuntu/Debian:
playwright install-deps chromium

# CentOS/RHEL:
yum install -y alsa-lib atk at-spi2-atk cups-libs libdrm libXcomposite libXdamage libXrandr mesa-gbme pango cairo
```

### 步骤 3: 配置环境变量

创建 `.env` 文件或直接设置环境变量：

```bash
# 接口测试配置
export POSTMAN_BASE_URL="http://your-test-server:port"
export POSTMAN_TOKEN="your-auth-token"  # 可选，留空使用自动登录
export POSTMAN_REPORTS_DIR="/data/reports"  # 报告输出目录

# UI 测试配置（可选，CLI 默认使用 headless 模式）
export UI_HEADLESS_BROWSER="chromium"  # chromium/firefox/webkit

# 飞书通知（可选）
export FEISHU_WEBHOOK="https://open.feishu.cn/open-apis/bot/v2/hook/xxx"
```

### 步骤 4: 准备冒烟清单（接口测试）

创建冒烟清单文件 `/data/collections/smoke_manifest.txt`：

```text
# 每行一个 Collection，格式：<路径> [env=<环境>] [data=<数据文件>]
/data/collections/01_核心流程.postman.json env=测试环境
/data/collections/02_支付链路.postman.json env=测试环境 data=/data/collections/users.csv
```

### 步骤 5: 测试执行

```bash
# 测试接口测试
python tools/scaffold/run_daily_smoke.py /data/collections/smoke_manifest.txt --output /data/reports/api

# 测试 UI 测试
python tools/scaffold/run_ui_tests.py --list  # 列出用例
python tools/scaffold/run_ui_tests.py --screenshots --output /data/reports/ui
```

### 步骤 6: 配置定时任务

#### Linux (crontab)

```bash
# 编辑 crontab
crontab -e

# 添加以下行（每天 21:00 执行接口测试，21:30 执行 UI 测试）
0 21 * * * cd /opt/seldom-api-testing && /usr/bin/python3 tools/scaffold/run_daily_smoke.py /data/collections/smoke_manifest.txt --output /data/reports/api >> /var/log/api-smoke.log 2>&1
30 21 * * * cd /opt/seldom-api-testing && /usr/bin/python3 tools/scaffold/run_ui_tests.py --screenshots --output /data/reports/ui >> /var/log/ui-test.log 2>&1
```

或使用配置脚本：

```bash
# 使用环境变量自定义时间
SMOKE_TIME="0 21 * * *" UI_TIME="30 21 * * *" ./tools/scaffold/setup_cron_tasks.sh --add
```

#### Windows (任务计划程序)

以管理员权限运行 PowerShell：

```powershell
cd C:\path\to\seldom-api-testing
.\tools\scaffold\setup_scheduled_tasks.ps1 -IncludeUITests -RunTime "21:00"
```

---

## 验证清单

部署后逐项验证：

- [ ] Python 版本 >= 3.10
- [ ] `pip install -r requirements.txt` 成功
- [ ] `playwright install chromium` 成功
- [ ] 环境变量已配置（BASE_URL、TOKEN 等）
- [ ] 冒烟清单文件存在且格式正确
- [ ] 接口测试 CLI 可手动执行成功
- [ ] UI 测试 CLI 可手动执行成功
- [ ] 定时任务已注册（`crontab -l` 或任务计划程序）
- [ ] 报告输出目录有写入权限
- [ ] 飞书推送（如配置）可正常接收

---

## 常见问题

### Q1: UI 测试在服务器上失败 "Browser closed"
**原因**: Linux 服务器缺少系统依赖  
**解决**: 执行 `playwright install-deps chromium`

### Q2: 接口测试返回 "base_url 格式无效"
**原因**: 环境变量未正确加载  
**解决**: 检查 `.env` 文件或 crontab 中的 `export` 语句

### Q3: 定时任务未执行
**Linux**: 
- 检查 crontab 语法: `crontab -l`
- 查看 cron 日志: `tail -f /var/log/cron`
- 确保 Python 路径正确: `which python3`

**Windows**:
- 检查任务计划程序中的任务状态
- 确保"不管用户是否登录都要运行"已勾选
- 检查"使用最高权限运行"

### Q4: 报告目录权限不足
**解决**: 
```bash
mkdir -p /data/reports
chmod 755 /data/reports
# 或在 crontab 中指定用户有权限的目录
```

### Q5: Playwright 浏览器下载失败
**原因**: 网络问题或 CDN 被墙  
**解决**: 
```bash
# 设置代理
export HTTPS_PROXY=http://proxy:port
playwright install chromium

# 或使用国内镜像
export PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright
playwright install chromium
```

---

## 监控建议

### 日志查看

```bash
# Linux
tail -f /var/log/api-smoke.log
tail -f /var/log/ui-test.log

# Windows
Get-Content D:\logs\api-smoke.log -Wait
```

### 执行结果检查

```bash
# 查看最新报告
ls -lt /data/reports/api/*.md | head -1
ls -lt /data/reports/ui/*.md | head -1

# 检查退出码（0=成功，1=失败）
echo $?
```

### 告警配置

建议在监控系统（如 Prometheus、Grafana、Zabbix）中添加：
- 定时任务执行状态监控
- 报告目录磁盘空间监控
- 飞书/邮件告警（失败时通知）

---

## 总结

**✅ 接口测试和 UI 测试的 CLI 执行已完全实现，可直接部署到服务器定时运行。**

关键确认：
1. ✅ 接口测试 CLI 已验证可在无 GUI 环境运行
2. ✅ UI 测试 CLI 使用 Playwright headless 模式，无需显示器
3. ✅ 所有配置支持环境变量覆盖
4. ✅ 定时任务脚本支持 Windows 和 Linux
5. ✅ 退出码正确，便于监控集成

**下一步**: 按照上述步骤部署到目标服务器并验证。
