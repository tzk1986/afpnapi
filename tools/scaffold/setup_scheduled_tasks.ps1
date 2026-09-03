# PowerShell 脚本：配置 Windows 计划任务执行每日冒烟测试
# 需要以管理员权限运行

param(
    [string]$TaskName = "DailySmokeTest",
    [string]$RunTime = "21:00",
    [string]$ProjectRoot = "",
    [switch]$IncludeUITests,
    [switch]$Remove
)

$ErrorActionPreference = "Stop"

# 获取项目根目录
if (-not $ProjectRoot) {
    $ProjectRoot = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
    if (-not $ProjectRoot -or -not (Test-Path (Join-Path $ProjectRoot "postman_api_tester"))) {
        $ProjectRoot = Get-Location
    }
}

Write-Host "项目目录: $ProjectRoot"

# Python 路径
$PythonPath = (Get-Command python).Source
if (-not $PythonPath) {
    Write-Error "找不到 Python，请确保已安装并添加到 PATH"
    exit 1
}
Write-Host "Python 路径: $PythonPath"

if ($Remove) {
    # 删除计划任务
    Write-Host "删除计划任务: $TaskName"
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    if ($IncludeUITests) {
        Unregister-ScheduledTask -TaskName "${TaskName}_UI" -Confirm:$false -ErrorAction SilentlyContinue
    }
    Write-Host "计划任务已删除"
    exit 0
}

# 创建接口测试冒烟任务
$SmokeScript = Join-Path $ProjectRoot "tools\scaffold\run_daily_smoke.py"

# 支持环境变量指定清单路径，或使用默认路径
$ManifestFile = $env:SMOKE_MANIFEST_FILE
if (-not $ManifestFile) {
    $ManifestFile = "D:\-11\11\auto-assets\collections\smoke_manifest.txt"
}

if (-not (Test-Path $SmokeScript)) {
    Write-Error "找不到冒烟测试脚本: $SmokeScript"
    exit 1
}

Write-Host "`n创建接口测试计划任务: $TaskName"
Write-Host "  执行时间: 每天 $RunTime"
Write-Host "  执行脚本: $SmokeScript"
Write-Host "  清单文件: $ManifestFile"

# 构建命令行参数
$TaskArgs = "`"$SmokeScript`""
if (Test-Path $ManifestFile) {
    $TaskArgs += " `"$ManifestFile`""
}
$TaskArgs += " --retries 1"

$TaskAction = New-ScheduledTaskAction `
    -Execute $PythonPath `
    -Argument $TaskArgs `
    -WorkingDirectory $ProjectRoot

$TaskTrigger = New-ScheduledTaskTrigger -Daily -At $RunTime

$TaskSettings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable

# 删除旧任务
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

# 注册新任务
Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $TaskAction `
    -Trigger $TaskTrigger `
    -Settings $TaskSettings `
    -Description "每日接口冒烟测试 - Postman API Tester" `
    -Force | Out-Null

Write-Host "  接口测试任务创建成功"

# 可选：创建 UI 测试任务
if ($IncludeUITests) {
    $UITaskName = "${TaskName}_UI"
    $UIScript = Join-Path $ProjectRoot "tools\scaffold\run_ui_tests.py"

    if (Test-Path $UIScript) {
        Write-Host "`n创建 UI 测试计划任务: $UITaskName"

        $UIAction = New-ScheduledTaskAction `
            -Execute $PythonPath `
            -Argument "`"$UIScript`" --screenshots" `
            -WorkingDirectory $ProjectRoot

        # UI 测试在接口测试之后 30 分钟执行
        $UITime = [DateTime]::ParseExact($RunTime, "HH:mm", $null).AddMinutes(30).ToString("HH:mm")
        $UITrigger = New-ScheduledTaskTrigger -Daily -At $UITime

        Unregister-ScheduledTask -TaskName $UITaskName -Confirm:$false -ErrorAction SilentlyContinue

        Register-ScheduledTask `
            -TaskName $UITaskName `
            -Action $UIAction `
            -Trigger $UITrigger `
            -Settings $TaskSettings `
            -Description "每日 UI 自动化测试 - Postman API Tester" `
            -Force | Out-Null

        Write-Host "  UI 测试任务创建成功 (执行时间: $UITime)"
    } else {
        Write-Warning "UI 测试脚本不存在: $UIScript"
    }
}

Write-Host "`n计划任务配置完成！"
Write-Host "查看任务: Get-ScheduledTask -TaskName '$TaskName*'"
Write-Host "手动执行: Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "删除任务: .\setup_scheduled_tasks.ps1 -Remove"
