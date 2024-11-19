import seldom


class TestRequest(seldom.TestCase):
    """
    前厅合作页面
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
        self.token = self.jsonpath("$..token", index=0)

    def end(self):
        print("结束测试")

    def test_cooperation_partner(self):
        """
        合作商列表
        """
        self.s.post(
            "/api/mer/cooperative/merchant/queryPage",
            json={"pageNum": 1, "pageSize": 10, "merchantId": "2021040701"},
            headers={"token": self.token},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)
        self.assertPath("message", "success")
        print(self.jsonpath("$.message", index=0))

        if self.jsonpath("$..errCode", index=0) == 0:
            print("查询成功")
        else:
            errCode = self.jsonpath("$..errCode", index=0)
            print("查询失败")
            print(f"查询失败的错误码是：{errCode}")

    def test_cooperation_department(self):
        """
        部门列表
        """
        self.s.post(
            "/api/mer/department/queryPage",
            json={
                "pageNum": 1,
                "pageSize": 10,
                "delFlag": 0,
                "merchantId": "2021040701",
            },
            headers={"token": self.token},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)
        self.assertPath("message", "success")

    def test_cooperation_position(self):
        """
        职务列表
        """
        self.s.post(
            "/api/mer/position/queryPage",
            json={
                "pageNum": 1,
                "pageSize": 10,
                "delFlag": 0,
                "merchantId": "2021040701",
            },
            headers={"token": self.token},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_cooperation_employee(self):
        """
        员工列表
        """
        self.s.post(
            "/api/us/employee/query/page",
            json={
                "pageNum": 1,
                "pageSize": 10,
                "delFlag": "",
                "sysId": "iom",
                "accountType": 2,
                "merchantId": "2021040701",
                "cooperativeMerchantCode": "",
            },
            headers={"token": self.token},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_cooperation_companyEmployeeGroup(self):
        """
        员工分组
        """
        self.s.post(
            "/api/mer/employee/group/queryPage",
            json={"pageNum": 1, "pageSize": 10, "merchantId": "2021040701"},
            headers={"token": self.token},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)


if __name__ == "__main__":
    seldom.main(
        # debug=True, 
        base_url="http://10.50.11.120:9001")
