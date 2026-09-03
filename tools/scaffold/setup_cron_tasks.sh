#!/bin/bash
# 配置 Linux/macOS cron 定时任务执行每日冒烟测试
# 用法: ./setup_cron_tasks.sh [--add|--remove|--list]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

PYTHON_BIN="${PYTHON_BIN:-python3}"
SMOKE_SCRIPT="$PROJECT_ROOT/tools/scaffold/run_daily_smoke.py"
UI_SCRIPT="$PROJECT_ROOT/tools/scaffold/run_ui_tests.py"

# 支持环境变量指定清单路径
MANIFEST_FILE="${SMOKE_MANIFEST_FILE:-${MANIFEST_FILE:-}}"

# 如果未指定清单文件，使用项目内的默认清单（需用户自行创建）
if [[ -z "$MANIFEST_FILE" ]]; then
    MANIFEST_FILE="$PROJECT_ROOT/smoke_manifest.txt"
    echo "提示: 未设置 SMOKE_MANIFEST_FILE，将使用默认路径: $MANIFEST_FILE"
    echo "      请确保该文件存在，或通过环境变量指定其他路径"
fi

# 默认执行时间（24小时制）
SMOKE_TIME="${SMOKE_TIME:-0 21 * * *}"      # 每天 21:00
UI_TIME="${UI_TIME:-30 21 * * *}"          # 每天 21:30

show_help() {
    echo "用法: $0 [--add|--remove|--list]"
    echo ""
    echo "选项:"
    echo "  --add       添加定时任务到 crontab"
    echo "  --remove    从 crontab 移除定时任务"
    echo "  --list      列出当前 crontab"
    echo ""
    echo "环境变量:"
    echo "  SMOKE_TIME  接口测试执行时间 (默认: '0 21 * * *')"
    echo "  UI_TIME     UI测试执行时间 (默认: '30 21 * * *')"
    echo "  MANIFEST_FILE 冒烟清单路径"
    echo ""
    echo "示例:"
    echo "  # 每天早上 9 点执行"
    echo "  SMOKE_TIME='0 9 * * *' $0 --add"
    echo ""
    echo "  # 仅工作日执行"
    echo "  SMOKE_TIME='0 21 * * 1-5' $0 --add"
}

add_cron_jobs() {
    echo "项目目录: $PROJECT_ROOT"
    echo "Python: $PYTHON_BIN"

    # 检查 Python
    if ! command -v "$PYTHON_BIN" &> /dev/null; then
        echo "错误: 找不到 Python ($PYTHON_BIN)" >&2
        exit 1
    fi

    # 获取当前 crontab
    CURRENT_CRON=$(crontab -l 2>/dev/null || true)

    # 添加接口测试任务
    if [[ -f "$SMOKE_SCRIPT" ]]; then
        SMOKE_JOB="$SMOKE_TIME cd $PROJECT_ROOT && $PYTHON_BIN $SMOKE_SCRIPT '$MANIFEST_FILE' --retries 1 >> logs/cron_smoke.log 2>&1"
        echo "添加接口测试任务: $SMOKE_TIME"
    else
        echo "警告: 冒烟测试脚本不存在: $SMOKE_SCRIPT" >&2
        SMOKE_JOB=""
    fi

    # 添加 UI 测试任务
    if [[ -f "$UI_SCRIPT" ]]; then
        UI_JOB="$UI_TIME cd $PROJECT_ROOT && $PYTHON_BIN $UI_SCRIPT --screenshots >> logs/cron_ui.log 2>&1"
        echo "添加 UI 测试任务: $UI_TIME"
    else
        echo "警告: UI 测试脚本不存在: $UI_SCRIPT" >&2
        UI_JOB=""
    fi

    # 确保日志目录存在
    mkdir -p "$PROJECT_ROOT/logs"

    # 构建新的 crontab 内容（先移除旧任务）
    NEW_CRON=$(echo "$CURRENT_CRON" | grep -v "# Postman API Tester" | grep -v "run_daily_smoke.py" | grep -v "run_ui_tests.py" || true)

    if [[ -n "$SMOKE_JOB" ]]; then
        NEW_CRON="$NEW_CRON
# Postman API Tester - 每日接口冒烟测试
$SMOKE_JOB"
    fi

    if [[ -n "$UI_JOB" ]]; then
        NEW_CRON="$NEW_CRON
# Postman API Tester - 每日 UI 测试
$UI_JOB"
    fi

    # 更新 crontab
    echo "$NEW_CRON" | crontab -

    echo ""
    echo "定时任务配置完成！"
    echo "当前 crontab:"
    crontab -l
}

remove_cron_jobs() {
    CURRENT_CRON=$(crontab -l 2>/dev/null || true)
    NEW_CRON=$(echo "$CURRENT_CRON" | grep -v "# Postman API Tester" | grep -v "run_daily_smoke.py" | grep -v "run_ui_tests.py" || true)
    echo "$NEW_CRON" | crontab -
    echo "定时任务已移除"
    crontab -l
}

list_cron_jobs() {
    echo "当前 crontab:"
    crontab -l 2>/dev/null || echo "(空)"
}

# 主逻辑
case "${1:-}" in
    --add)
        add_cron_jobs
        ;;
    --remove)
        remove_cron_jobs
        ;;
    --list)
        list_cron_jobs
        ;;
    -h|--help|help)
        show_help
        ;;
    *)
        show_help
        exit 1
        ;;
esac
