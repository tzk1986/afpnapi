import seldom


class TestRequest(seldom.TestCase):
    """
    前厅食安页面
    """

    def start(self):
        print("开始测试")
        self.s = self.Session()
        self.s.post(
            "/api/uims/login",
            json={
                "systemName": "ifood-operating-manage",
                "authenType": 1,
                "password": "123456",
                "phoneNumber": "18930410921",
                "smsCode": "",
                "kaptchaCode": "1",
                "kaptchaKey": "65eb74b59e224db1b8f6ba3266848380",
            },
        )
        self.assertStatusCode(200)
        print("登录成功")

    def end(self):
        print("结束测试")

    def test_foodsafety_health(self):
        """
        健康证
        """
        tt = self.jsonpath("$..token", index=0)
        print(tt)
        self.s.post(
            "/api/mer/healthCert/queryPage",
            json={
                "pageNum": 1,
                "pageSize": 10,
                "merchantId": "2021040701",
                "storeId": None,
                "healthExpireStartTime": None,
                "healthExpireEndTime": None,
            },
            headers={"token": tt},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_foodsafety_post(self):
        """
        岗位管理
        """
        tt = self.jsonpath("$..token", index=0)
        print(tt)
        self.s.post(
            "/api/mer/healthPost/queryPage",
            json={
                "pageNum": 1,
                "postId": "",
                "pageSize": 10,
                "merchantId": "2021040701",
            },
            headers={"token": tt},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)


if __name__ == "__main__":
    seldom.main(
        # debug=True,
        base_url="http://10.50.11.120:9001"
    )
