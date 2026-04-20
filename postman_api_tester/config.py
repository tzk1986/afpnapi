#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Postman API 测试配置文件

在此处填写测试所需的配置信息。
token 优先级：命令行参数 > 此文件中的 TOKEN > 自动登录获取
"""

# ==============================================================
# 认证 Token 配置
# 将登录后获取的 token 填写在这里，测试时将自动使用此 token。
# 设为空字符串 "" 则使用自动登录获取 token（可能因账号问题失败）。
# "ZDdlMzVlNzA4NDUwMDhiNjQ5YmJhYWE2OTIyMTMzNWU.dXBzLXdlYg==.ZDZmZDQwYjIzN2M0MGE1OTgxZWQxMTAyMGMxMDE5NjM"
# 
# ==============================================================
TOKEN = "ZDdlMzVlNzA4NDUwMDhiNjQ5YmJhYWE2OTIyMTMzNWU.dXBzLXdlYg==.ZGUxMzg2YWRjMjNlODdhZWEwMDQ4ZjEwMjk4NWNiMzY"

# ==============================================================
# 测试目标地址
# 设置后 run_postman_tests() 不指定 base_url 时使用此地址。
# 示例: BASE_URL = "http://10.50.11.120:8090"
# "http://10.50.11.130:11000"
# ==============================================================
BASE_URL = "http://10.50.11.130:11000"

# ==============================================================
# 报告输出目录配置（可选）
# 为空字符串时，默认输出到项目根目录下的 reports 文件夹。
# 可配置绝对路径，例如：r"D:\\api-test-reports"
# ============================================================== 
REPORT_OUTPUT_DIR = ""
