import seldom


class TestRequest(seldom.TestCase):
    """
    前厅会员列表页面
    """

    def start(self):
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
        print(self.s)
        self.token = self.jsonpath("$..token", index=0)

    def test_query_userInfos(self):
        """
        会员列表
        """
        self.s.post(
            "/api/query/userInfos",
            json={
                "userBackStatus": "0",
                "phoneNumber": "",
                "nickName": "",
                "memberCard": "",
                "merchantId": "2021040701",
                "pageNum": 1,
                "delFlag": 0,
                "pageSize": 10,
                "sysId": "iom",
            },
            headers={"token": self.token},
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

    def test_faceAi_getUserInfos(self):
        """
        会员列表-人脸列表
        """
        self.s.post(
            "/api/faceAi/getUserInfos",
            json={
                "pageNum": 1,
                "pageSize": 10,
                "delFlag": 0,
                "departmentName": "",
                "merchantName": "",
                "merchantId": "2021040701",
                "cooperativeMerchantId": "",
                "dimission": "",
                "phoneNumber": "",
            },
            headers={"token": self.token},
        )
        self.jsonpath("$.message")
        print(self.jsonpath("$.message"))
        self.assertPath("message", "success")

    def test_accountBalance_insertAccountBalanceAdd(self):
        """
        会员列表-开通账户
        """
        self.s.post(
            "/api/ts/accountBalance/insertAccountBalanceAdd",
            json={
                "accountType": 1,
                "phoneNumber": "15900506254",
                "cashBalance": "",
                "merchantId": "2021040701",
            },
            headers={"token": self.token},
        )
        self.assertPath("message", "会员钱包已存在")


if __name__ == "__main__":
    seldom.main(debug=True, base_url="http://10.50.11.120:9001")
