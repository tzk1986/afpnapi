import seldom


class TestRequest(seldom.TestCase):
    """
    前厅菜品页面
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

    def test_system_loginLog(self):
        """
        登录日志
        """
        tt = self.jsonpath("$..token", index=0)
        print(tt)
        self.s.post(
            "/api/oplog/queryPage",
            json={
                "logType": 2,
                "merchantId": "2021040701",
                "moduleCode": "",
                "systemType": "",
            },
            headers={"token": tt},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_system_operateLog(self):
        """
        操作日志
        """
        tt = self.jsonpath("$..token", index=0)
        print(tt)
        self.s.post(
            "/api/oplog/queryPage",
            json={
                "logType": 1,
                "merchantId": "2021040701",
                "moduleCode": "",
                "systemType": "",
            },
            headers={"token": tt},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_system_settings1(self):
        """
        设置-支付配置
        """
        tt = self.jsonpath("$..token", index=0)
        print(tt)
        payload = {
            "merchantId":"2021040701",
        }
        self.s.get(
            "/api/get/recharge/switch",
            params=payload,
            headers={"token": tt},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_system_settings2(self):
        """
        设置-绑盘配置
        """
        tt = self.jsonpath("$..token", index=0)
        print(tt)
        payload = {
            "merchantId":"2021040701",
        }
        self.s.get(
            "/api/mer/merchantlimitconfig/query",
            params=payload,
            headers={"token": tt},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_system_settings3(self):
        """
        设置-视觉餐厅配置
        """
        tt = self.jsonpath("$..token", index=0)
        print(tt)
        self.s.post(
            "/api/base/org/config/queryConfig",
            json={
                "modelCode": "food_visualreg_config",
                "organizationId": "2021040701",
                "organizationType": 22,
            },
            headers={"token": tt},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_system_settings4(self):
        """
        设置-移动端首页展示
        """
        tt = self.jsonpath("$..token", index=0)
        print(tt)
        self.s.post(
            "/api/base/org/config/queryConfig",
            json={
                "modelCode": "merchant_applet_config",
                "organizationId": "2021040701",
                "organizationType": 22,
            },
            headers={"token": tt},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_system_settings3(self):
        """
        设置-菜品新增编辑
        """
        tt = self.jsonpath("$..token", index=0)
        print(tt)
        self.s.post(
            "/api/base/org/config/queryConfig",
            json={
                "modelCode": "update_food_config",
                "organizationId": "2021040701",
                "organizationType": 22,
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
