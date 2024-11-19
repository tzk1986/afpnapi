import seldom


class TestRequest(seldom.TestCase):
    """
    前厅菜品页面
    """

    def start(self):
        print("开始测试")
        self.s = self.Session()
        self.s.post(
            "/api/auth/login/login",
            json={
                "systemName": "ifood-supplier",
                "authenType": 1,
                "phoneNumber": "18930410921",
                "loginType": 1,
                "password": "123456",
                "kaptchaCode": "1",
                "kaptchaKey": "16e0143457e04ff3b19bab2e60101bf0",
            },
        )
        self.assertStatusCode(200)
        print("登录成功")
        self.token = self.jsonpath("$..token", index=0)

    def end(self):
        print("结束测试")

    def test_dataReport_storeReceiveStatistics(self):
        """
        数据报表-档口领用统计
        """
        payload = {"startDate": "20241019", "endDate": "20241118"}
        self.s.post(
            "/api/stat/outboundMaterialStat/queryTakeoutCollectDayResult",
            json=payload,
            headers={"token": self.token},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)


if __name__ == "__main__":
    seldom.main(
        # debug=True,
        base_url="http://10.50.11.120:9005"
    )   
