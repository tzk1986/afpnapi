import seldom


class TestRequest(seldom.TestCase):
    """
    前厅财务页面
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

    def test_financial_flow(self):
        """
        订单列表
        """
        self.s.post(
            "/api/ts/orderRecord/queryPage",
            json={
                "coorprateId": "",
                "userName": "",
                "userId": "",
                "storeId": "",
                "storeIds": [],
                "amountTypeList": [],
                "accountTypeList": [],
                "billTypeList": [],
                "startDate": "2024-11-13T16:00:00.000Z",
                "endDate": "2024-11-14T15:59:59.999Z",
                "payChannelType": None,
                "billType": None,
                "amountType": None,
                "accountType": None,
                "merchantId": "2021040701",
                "pageNum": 1,
                "delFlag": 0,
                "pageSize": 10,
                "cooperateCode": None,
                "phoneNumber": "",
                "employeeName": "",
                "departmentName": "",
                "foodCard": "",
                "positionName": "",
                "employeeCode": "",
            },
            headers={"token": self.token},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)
        self.assertPath("message", "success")
        print(self.jsonpath("$.message", index=0))

        if self.jsonpath("$..errCode", index=0) == 0:
            print("查询成功")
            num = self.jsonpath("$.data.totalCount", index=0)
            print(f"查询到的总数量是：{num}")
        else:
            errCode = self.jsonpath("$..errCode", index=0)
            print("查询失败")
            print(f"查询失败的错误码是：{errCode}")

    def test_financial_merchant(self):
        """
        商户对账
        """
        self.s.post(
            "/api/ts/businessCheck/page",
            json={
                "exportType": "charge_withdrawek_deduct_check",
                "sumType": "1",
                "mealType": "",
                "isMealTypeQuery": 2,
                "queryType": 1,
                "sysId": "iom",
                "sumLevel": 1,
                "merchantIds": [],
                "startDate": "2024-11-13T16:00:00.000Z",
                "endDate": "2024-11-14T15:59:59.999Z",
                "merchantId": "2021040701",
                "pageNum": 1,
                "pageSize": 10,
            },
            headers={"token": self.token},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_financial_store(self):
        """
        档口对账
        """
        self.s.post(
            "/api/ts/businessCheck/page",
            json={
                "sumType": "1",
                "mealType": "",
                "storeIds": None,
                "isMealTypeQuery": 2,
                "queryType": 2,
                "sysId": "iom",
                "chargeWithdrawType": None,
                "sumLevel": 2,
                "startDate": "2024-11-13T16:00:00.000Z",
                "endDate": "2024-11-14T15:59:59.999Z",
                "accountType": None,
                "merchantIds": ["2021040701"],
                "treeGroupId": None,
                "pageNum": 1,
                "pageSize": 10,
                "businessType": 1,
            },
            headers={"token": self.token},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_financial_partner(self):
        """
        合作商消费对账
        """
        self.s.post(
            "/api/ts/businessCheck/enterprise/page",
            json={
                "exportType": None,
                "sumType": "1",
                "mealType": None,
                "cooperateCodeList": [],
                "phoneNumber": None,
                "employeeCode": None,
                "employeeName": None,
                "departmentName": None,
                "positionName": None,
                "isMealTypeQuery": 2,
                "queryType": 3,
                "sysId": "iom",
                "sumLevel": 1,
                "excelType": 1,
                "startDate": "2024-11-13T16:00:00.000Z",
                "endDate": "2024-11-14T15:59:59.999Z",
                "treeGroupId": None,
                "storeIds": None,
                "merchantIds": ["2021040701"],
                "pageNum": 1,
                "pageSize": 10,
                "businessType": None,
            },
            headers={"token": self.token},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_financial_subsidyDeduction(self):
        """
        补贴下发扣除对账
        """
        self.s.post(
            "/api/ts/subsidyCheck/queryPage",
            json={
                "exportType": None,
                "sumType": "1",
                "mealType": None,
                "cooperateCodeList": [],
                "phoneNumber": None,
                "employeeCode": None,
                "employeeName": None,
                "departmentName": None,
                "positionName": None,
                "isMealTypeQuery": 2,
                "queryType": 3,
                "sysId": "iom",
                "sumLevel": 1,
                "excelType": 1,
                "startDate": "2024-11-13T16:00:00.000Z",
                "endDate": "2024-11-14T15:59:59.999Z",
                "merchantIds": ["2021040701"],
                "pageNum": 1,
                "pageSize": 10,
            },
            headers={"token": self.token},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_financial_self(self):
        """
        企业员工对账
        """
        self.s.post(
            "/api/ts/cooperate/consume/queryPage",
            json={
                "exportType": None,
                "sumType": "1",
                "mealType": None,
                "cooperateCode": None,
                "cooperateCodeList": [],
                "phoneNumber": None,
                "employeeCode": None,
                "employeeName": None,
                "departmentName": None,
                "positionName": None,
                "isMealTypeQuery": 2,
                "queryType": 3,
                "sysId": "iom",
                "sumLevel": 1,
                "excelType": 1,
                "startDate": "2024-11-13T16:00:00.000Z",
                "endDate": "2024-11-14T15:59:59.999Z",
                "merchantId": "2021040701",
                "pageNum": 1,
                "pageSize": 10,
                "businessType": None,
            },
            headers={"token": self.token},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_financial_reducecount(self):
        """
        减免次数统计
        """
        self.s.post(
            "/api/employee/derate/summary",
            json={
                "sumType": "1",
                "userType": "2",
                "cooperativeMerchantId": None,
                "phoneNumber": None,
                "employeeCode": None,
                "employeeName": None,
                "departmentName": None,
                "positionName": None,
                "startDate": "2024-11-13T16:00:00.000Z",
                "endDate": "2024-11-14T15:59:59.999Z",
                "merchantId": "2021040701",
                "sysId": "iom",
                "pageNum": 1,
                "pageSize": 10,
            },
            headers={"token": self.token},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_financial_shop(self):
        """
        商城对账
        """
        self.s.post(
            "/api/ts/busines/shop/sum",
            json={
                "sumType": "1",
                "sysId": "iom",
                "startDate": "2024-11-13T16:00:00.000Z",
                "endDate": "2024-11-14T15:59:59.999Z",
                "merchantId": None,
                "extMerchantId": None,
                "merchantIds": [],
                "pageNum": 1,
                "pageSize": 10,
            },
            headers={"token": self.token},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_financial_channelcollection(self):
        """
        渠道收款统计
        """
        self.s.post(
            "/api/query/dwdPayChannelAmountD/sum",
            json={
                "payChannelType": None,
                "exportType": None,
                "sumType": "1",
                "startDate": "2024-11-13T16:00:00.000Z",
                "endDate": "2024-11-14T15:59:59.999Z",
                "merchantIds": ["2021040701"],
                "pageNum": 1,
                "pageSize": 10,
                "sysId": "iom",
            },
            headers={"token": self.token},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)


if __name__ == "__main__":
    seldom.main(
        # debug=True,
        base_url="http://10.50.11.120:9001"
    )
