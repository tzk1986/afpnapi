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
        
        
    def test_Afpn_001_1(self):
        """
        登录
        """
        BaseUrl = "http://10.50.11.120:9001"
        print(f"{BaseUrl}/login")
        s = Steps().open(f"{BaseUrl}/login")
        s.sleep(2)

        s.find("#app > div > form > div:nth-child(2) > div > div > input").type(
            "18335161013"
        )
        s.find("#app > div > form > div:nth-child(3) > div > div > input").type(
            "112233"
        )
        s.find(
            "#app > div > form > div:nth-child(4) > div > div > div.login-input-code.el-input.el-input--prefix > input"
        ).type("1")
        s.find("#app > div > form > div:nth-child(5) > div > button").click()
        s.sleep()
        self.get_cookies()
        print(self.get_cookies())
        s.open(f"{BaseUrl}/merchant/merchantList")
        s.sleep()
        # 商户简称搜索
        s.find(
            "#app > section > section > section > main > section > section > main > div.main > div.s-card > div > div.search_option_left.s-gap-6-15 > div:nth-child(2) > div > input"
        ).type(f"{MerchantName}")
        s.sleep()
        # 选择跳转到餐厅
        s.find(
            "#app > section > section > section > main > section > section > main > div.main > div.table_content > div.el-table.el-table--fit.el-table--scrollable-x.el-table--enable-row-transition > div.el-table__fixed-right > div.el-table__fixed-body-wrapper > table > tbody > tr > td.el-table_1_column_7.el-table__cell > div > button:nth-child(4) > span"
        ).click()
        s.sleep(3)
        s.switch_to_window(1)
        self.get_cookies()
        print(self.get_cookies())
        cookies = self.get_cookies()
        for cookie in cookies:
            self.token = cookie['value']
            # 在这里可以对 value 进行处理或打印
            print(self.token)
        
        
    # def test_Afpn_001_2(self):
    #     """
    #     会员列表
    #     """
    #     self.post(
    #         "http://10.50.11.120:9001/api/query/userInfos",
    #         json={
    #             "userBackStatus": "0",
    #             "phoneNumber": "",
    #             "nickName": "",
    #             "memberCard": "",
    #             "merchantId": "2021040701",
    #             "pageNum": 1,
    #             "delFlag": 0,
    #             "pageSize": 10,
    #             "sysId": "iom",
    #         },
    #         headers={"token": self.token},
    #     )
    #     self.assertStatusCode(200)
    #     self.assertPath("errCode", 0)

    #     self.assertJSON(0, self.jsonpath("$..errCode", index=0))
    #     self.assertPath("message", "success")

    #     print(self.jsonpath("$.message", index=0))

    #     if self.jsonpath("$..errCode", index=0) == 0:
    #         print("查询成功")
    #     else:
    #         errCode = self.jsonpath("$..errCode", index=0)
    #         print("查询失败")
    #         print(f"查询失败的错误码是：{errCode}")

    # def start(self):
    #     self.s = self.Session()
    #     self.s.get('/cookies/set/sessioncookie/123456789')

    # def test_get_cookie1(self):
    #     self.s.get('/cookies')

    # def test_get_cookie2(self):
    #     self.s.get('/cookies')


if __name__ == '__main__':
    # seldom.main(debug=True, base_url="https://httpbin.org")
    seldom.main(
        debug=True, 
        # base_url="http://10.50.11.120:9001"
        )