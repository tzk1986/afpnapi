#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
快速测试运行脚本 - 一键运行测试和打开报告
版本: 1.0.2
"""

import os
import socket
import sys
import webbrowser
from pathlib import Path

# 获取项目根目录（脚本所在目录的父目录）
PROJECT_ROOT = Path(__file__).parent.parent
os.chdir(PROJECT_ROOT)

# 添加包路径
sys.path.insert(0, str(PROJECT_ROOT))

from postman_api_tester.postman_api_tester import run_postman_tests
from postman_api_tester import config as cfg


def get_local_ip() -> str:
    """获取本机局域网IP，便于同网段访问报告服务。"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def main():
    """主函数"""
    print("\n" + "="*80)
    print("Postman API 快速测试工具".center(80))
    print("="*80)
    
    # 获取Postman文件列表
    postman_files = [f for f in os.listdir('.') if f.endswith('.postman.json') or f.endswith('.json')]
    
    if not postman_files:
        print("\n✗ 未找到Postman JSON文件!")
        print("请将Postman导出的JSON文件放在当前目录")
        return
    
    print("\n📁 找到以下Postman文件:")
    for idx, file in enumerate(postman_files, 1):
        print(f"  {idx}. {file}")
    
    # 选择文件
    while True:
        try:
            choice = input(f"\n请选择文件 (1-{len(postman_files)}) [默认: 1]: ").strip()
            if not choice:
                choice = '1'
            idx = int(choice) - 1
            if 0 <= idx < len(postman_files):
                postman_file = postman_files[idx]
                break
            else:
                print(f"✗ 请输入1-{len(postman_files)}之间的数字")
        except ValueError:
            print("✗ 请输入有效的数字")
    
    # 可选：输入基础URL
    base_url = input("\n请输入基础URL (可选，按回车跳过): ").strip()
    if not base_url:
        base_url = None

    # 可选：输入报告输出目录
    default_report_dir = getattr(cfg, "REPORT_OUTPUT_DIR", "").strip() or str(PROJECT_ROOT / "reports")
    report_dir_input = input(f"\n请输入报告输出目录 (可选，默认: {default_report_dir}): ").strip()
    output_dir = report_dir_input or default_report_dir
    
    # 可选：选择每页显示条数
    print("\n📊 每页显示条数选项:")
    print("  1. 20条 (默认)")
    print("  2. 30条")
    print("  3. 50条")
    print("  4. 100条")
    
    page_sizes = {1: 20, 2: 30, 3: 50, 4: 100}
    while True:
        try:
            choice = input("\n请选择每页显示条数 (1-4) [默认: 1]: ").strip()
            if not choice:
                choice = '1'
            page_choice = int(choice)
            if 1 <= page_choice <= 4:
                results_per_page = page_sizes[page_choice]
                break
            else:
                print("✗ 请选择1-4之间的选项")
        except ValueError:
            print("✗ 请输入有效的数字")
    
    # 运行测试
    print(f"\n▶ 开始运行测试...")
    print(f"  文件: {postman_file}")
    if base_url:
        print(f"  基础URL: {base_url}")
    print(f"  每页显示: {results_per_page}条")
    
    try:
        report = run_postman_tests(
            postman_file,
            base_url=base_url,
            output_dir=output_dir,
            results_per_page=results_per_page,
        )

        # 获取完整路径
        report_path = os.path.abspath(report.generated_report_file)
        
        print(f"\n✓ 测试完成！")
        print(f"✓ 报告已生成: {report_path}")
        print(f"✓ 报告输出目录: {os.path.abspath(output_dir)}")
        
        # 启动Flask服务器
        print("\n🚀 启动报告服务器...")
        try:
            import subprocess
            import signal
            import time
            
            # 启动Flask服务器
            server_cmd = [sys.executable, str(PROJECT_ROOT / 'report_server.py')]
            server_process = subprocess.Popen(server_cmd, cwd=PROJECT_ROOT)
            
            # 等待服务器启动
            time.sleep(2)
            
            # 打开浏览器
            webbrowser.open('http://localhost:5000')
            local_ip = get_local_ip()
            print("✓ 已在浏览器中打开报告 (http://localhost:5000)")
            print("✓ 服务器正在后台运行，支持Token测试和重新请求功能")
            print(f"✓ 局域网访问地址: http://{local_ip}:5000")
            
            print("\n💡 使用提示:")
            print("  • 首页可查看历史报告列表并选择两份报告做差异对比")
            print("  • 在首页直接查看测试结果表格")
            print("  • 使用下拉菜单改变每页显示的数据条数")
            print("  • 点击状态筛选按钮过滤结果")
            print("  • 点击'展开'按钮查看每个API的详细请求/响应信息")
            print("  • 点击页码快速导航到指定页面")
            print("  • 输入Token并点击'测试Token'验证有效性")
            print("  • 在详情中点击'重新请求'按钮使用新Token重新测试API")
            print("  • 同局域网开发可通过上面的局域网地址直接访问报告中心")
            print(f"  • 当前报告目录: {os.path.abspath(output_dir)}")
            print("\n按 Ctrl+C 停止服务器...")
            
            # 等待用户中断
            try:
                server_process.wait()
            except KeyboardInterrupt:
                print("\n🛑 正在停止服务器...")
                server_process.terminate()
                server_process.wait()
                print("✓ 服务器已停止")
                
        except Exception as e:
            print(f"✗ 启动服务器失败: {e}")
            print("将直接打开HTML文件...")
            webbrowser.open('file://' + report_path)
            print("✓ 已在浏览器中打开报告")
            print("注意：Token测试和重新请求功能需要服务器支持")
        
    except Exception as e:
        print(f"\n✗ 测试执行失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()
