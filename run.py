import seldom

# 测试环境地址
test_url ="http://10.50.11.120:9001"


if __name__ == '__main__':
    seldom.main(
        path="./test_dir/test_afpn",  # 运行用例目录
        base_url=test_url,  # 基础URL地址
        tester="tzk",  # 测试人员
        # debug=True,  # 是否调试模式
        
        # rerun=3   # 重跑次数
    )
