import seldom
from seldom import Steps

# 商户简称
MerchantName ="艾佩"

class TestRequest(seldom.TestCase):
    """
    前厅会员列表页面
    """

    def start(self):
        
        print("测试开始")
        
        
    
        
    def test_Afpn_001_2(self):
        """
        会员列表
        """
        self.post(
            "http://10.50.11.120:9001/api/order/queryPage",

        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

        self.assertJSON(0, self.jsonpath("$..errCode", index=0))
        self.assertPath("message", "success")

        print(self.jsonpath("$.message", index=0))

        if self.jsonpath("$..errCode", index=0) == 0:
            print("查询成功")
        else:
            errCode = self.jsonpath("$..errCode", index=0)
            print("查询失败")
            print(f"查询失败的错误码是：{errCode}")




if __name__ == '__main__':
    # seldom.main(debug=True, base_url="https://httpbin.org")
    seldom.main(
        debug=True, 
        # base_url="http://10.50.11.120:9001"
        )