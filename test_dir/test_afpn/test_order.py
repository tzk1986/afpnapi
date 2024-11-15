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

    def end(self):
        print("结束测试")

    def test_order_offline(self):
        """
        订单列表
        """
        tt = self.jsonpath("$..token", index=0)
        print(tt)
        self.s.post(
            "/api/order/queryPage",
            json={
                "merchantId": "2021040701",
                "cooperativeMerchantCode": None,
                "sysId": "iom",
                "departmentIdList": [],
                "positionIdList": [],
                "storeIds": [],
                "departId": None,
                "queryTimeType": 0,
                "orderStatusList": ["2", "3", "6", "9", "10"],
                "orderOriginalList": ["3", "4", "5", "6", "10", "11"],
                "orderType": 1,
                "refundStatus": None,
                "createTime": None,
                "startDate": "2024-11-13T16:00:00.000Z",
                "endDate": "2024-11-14T15:59:59.999Z",
                "mealType": None,
                "pageNum": 1,
                "delFlag": 0,
                "pageSize": 10,
                "reserveStatusList": [],
                "foodCard": None,
            },
            headers={"token": tt},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)
        self.assertPath("message", "success")
        print(self.jsonpath("$.message", index=0))

        if self.jsonpath("$..errCode", index=0) == 0:
            print("查询成功")
            num = self.jsonpath("$.data.totalCount", index=0)
            print(f"查询到的订单总数量是：{num}")
        else:
            errCode = self.jsonpath("$..errCode", index=0)
            print("查询失败")
            print(f"查询失败的错误码是：{errCode}")

    def test_order_refund(self):
        """
        退款审核
        """
        tt = self.jsonpath("$..token", index=0)
        print(tt)
        self.s.post(
            "/api/ts/applyRefund/queryPage",
            json={
                "storeId": None,
                "orderStatus": None,
                # 1 待审核 2 驳回 3 已通过 4 处理中
                "refundStatus": 1,
                "createTime": None,
                "orderCode": None,
                "mealType": None,
                "startDate": None,
                "endDate": None,
                "pageNum": 1,
                "delFlag": 0,
                "pageSize": 10,
                "cooperateCode": None,
                "merchantId": "2021040701",
                "phoneNumber": "",
            },
            headers={"token": tt},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_order_feedtakemeals(self):
        """
        投取餐管理
        """
        tt = self.jsonpath("$..token", index=0)
        print(tt)
        self.s.post(
            "/api/order/mealManage",
            json={
                "sysId": "iom",
                "merchantList": [],
                "storeIds": [],
                "mealStatus": "0",
                "startDate": "2024-11-13T16:00:00.000Z",
                "endDate": "2024-11-14T15:59:59.999Z",
                "merchantId": "2021040701",
                "pageNum": 1,
                "pageSize": 10,
            },
            headers={"token": tt},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_order_delivery(self):
        """
        配送单管理
        """
        tt = self.jsonpath("$..token", index=0)
        print(tt)
        self.s.post(
            "/api/ts/orderDelivery/queryPage",
            json={
                "sysId": "imm",
                "storeId": None,
                "areaId": None,
                "deliveryStatus": 1,
                "name": None,
                "phoneNumber": None,
                "startDate": "2024-11-13T16:00:00.000Z",
                "endDate": "2024-11-14T15:59:59.999Z",
                "merchantId": "2021040701",
                "pageNum": 1,
                "pageSize": 10,
            },
            headers={"token": tt},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_prepareMeal(self):
        """
        备取餐管理
        """
        tt = self.jsonpath("$..token", index=0)
        print(tt)
        self.s.post(
            "/api/mer/store/queryPage",
            json={
                "pageNum": 1,
                "pageSizeZero": True,
                "pageSize": 0,
                "merchantId": "2021040701",
            },
            headers={"token": tt},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)


if __name__ == "__main__":
    seldom.main(debug=True, base_url="http://10.50.11.120:9001")
