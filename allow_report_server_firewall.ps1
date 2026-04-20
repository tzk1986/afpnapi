[CmdletBinding()]
param(
    [int]$Port = 5000,
    [string]$RuleName = "Postman Report Server 5000"
)

$ErrorActionPreference = "Stop"

function Test-IsAdministrator {
    $currentIdentity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($currentIdentity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Ensure-Administrator {
    if (Test-IsAdministrator) {
        return
    }

    Write-Host "正在申请管理员权限以放通 Windows 防火墙端口 $Port ..."
    $argumentList = @(
        "-NoProfile"
        "-ExecutionPolicy"
        "Bypass"
        "-File"
        ('"{0}"' -f $PSCommandPath)
        "-Port"
        $Port
        "-RuleName"
        ('"{0}"' -f $RuleName)
    )

    Start-Process -FilePath "powershell.exe" -Verb RunAs -ArgumentList $argumentList | Out-Null
    exit 0
}

function Ensure-FirewallRule {
    param(
        [string]$DisplayName,
        [string]$Direction
    )

    $existingRule = Get-NetFirewallRule -DisplayName $DisplayName -ErrorAction SilentlyContinue
    if ($existingRule) {
        Set-NetFirewallRule -DisplayName $DisplayName -Enabled True -Action Allow -Profile Any | Out-Null
        Write-Host "已存在规则，已确认启用: $DisplayName"
        return
    }

    New-NetFirewallRule \
        -DisplayName $DisplayName \
        -Direction $Direction \
        -Action Allow \
        -Protocol TCP \
        -LocalPort $Port \
        -Profile Any | Out-Null

    Write-Host "已创建规则: $DisplayName"
}

Ensure-Administrator

Ensure-FirewallRule -DisplayName $RuleName -Direction Inbound

$ruleSummary = Get-NetFirewallRule -DisplayName $RuleName |
    Get-NetFirewallPortFilter |
    Select-Object @{Name = 'RuleName'; Expression = { $RuleName } }, Protocol, LocalPort

Write-Host ""
Write-Host "Windows 防火墙已放通报告服务端口。"
$ruleSummary | Format-Table | Out-String | Write-Host
Write-Host "现在可通过 http://本机IP:$Port 供同局域网访问。"