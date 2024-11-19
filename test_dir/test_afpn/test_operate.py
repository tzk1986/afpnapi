import seldom


class TestRequest(seldom.TestCase):
    """
    前厅运营页面
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

    def test_operate_withdraw(self):
        """
        提现管理
        """
        self.s.post(
            "/api/ts/withDrawl/queryPage",
            json={
                "sysId": "iom",
                "pageNum": 1,
                "pageSize": 10,
                "date": [],
                "phoneNumber": None,
                "startDate": "2024-11-13T16:00:00.000Z",
                "endDate": "2024-11-14T15:59:59.999Z",
                "merchantId": "2021040701",
                "exportType": "withdraw",
                "reviewerVerdict": 0,
            },
            headers={"token": self.token},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_operate_subsidyallot(self):
        """
        补贴下发
        """
        self.s.post(
            "/api/ts/subsidy/queryPageExample",
            json={
                "subsidyId": "",
                "subsidyDate": "",
                "merchantId": "2021040701",
                "storeId": "",
                "subsidyName": "",
                "subsidyMode": "",
                "subsidyStatus": "",
                "delFlag": 0,
                "pageNum": 1,
                "pageSize": 10,
            },
            headers={"token": self.token},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_operate_subsidydeduct(self):
        """
        补贴扣除
        """
        self.s.post(
            "/api/ts/subsidyDeduct/queryPage",
            json={
                "subsidyId": "",
                "createTime": "",
                "merchantId": "2021040701",
                "storeId": "",
                "subsidyDeductName": "",
                "subsidyMode": "",
                "execResult": None,
                "delFlag": 0,
                "pageNum": 1,
                "pageSize": 10,
                "corpId": "",
            },
            headers={"token": self.token},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_operate_subsidyrules(self):
        """
        补贴规则
        """
        self.s.post(
            "/api/subsidy/querySubsidyPage",
            json={
                "merchantId": "2021040701",
                "storeId": "",
                "dryingTime": None,
                "subsidyConfigName": "",
                "subsidyStatus": "",
                "queryDate": "",
                "delFlag": 0,
                "pageNum": 1,
                "pageSize": 10,
            },
            headers={"token": self.token},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_operate_deductrules(self):
        """
        减免规则
        """
        self.s.post(
            "/api/ts/quotaconfig/queryPage",
            json={
                "merchantId": "2021040701",
                "storeId": "",
                "quotaConfigName": "",
                "quotaStatus": "",
                "queryDate": "",
                "delFlag": 0,
                "pageNum": 1,
                "pageSize": 10,
            },
            headers={"token": self.token},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_operate_bindlimit(self):
        """
        绑盘限制
        """
        self.s.post(
            "/api/ts/bindTrayRule/queryPage",
            json={
                "pageNum": 1,
                "pageSize": 10,
                "merchantId": "2021040701",
                "ruleName": "",
            },
            headers={"token": self.token},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_operate_reservation(self):
        """
        预定管理
        """
        self.s.post(
            "/api/mer/store/queryPageExample/two",
            json={"pageNum": 1, "pageSize": 8, "merchantId": "2021040701"},
            headers={"token": self.token},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_operate_rechargewelfare(self):
        """
        充值福利
        """
        self.s.post(
            "/api/ts/welfare/queryPageExample",
            json={
                "createTime": None,
                "welfareName": None,
                "createBy": None,
                "status": None,
                "delFlag": 0,
                "pageNum": 1,
                "pageSize": 10,
                "merchantId": "2021040701",
            },
            headers={"token": self.token},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_operate_consumetimes(self):
        """
        消费次数
        """
        self.s.post(
            "/api/mer/consumption/times/queryPage",
            json={
                "merchantId": "2021040701",
                "storeId": "",
                "consumptionTimesName": "",
                "quotaStatus": "",
                "queryDate": "",
                "pageNum": 1,
                "pageSize": 10,
            },
            headers={"token": self.token},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_operate_offlinetickets(self):
        """
        线下餐券
        """
        self.s.post(
            "/api/mer/mealticket/queryPage",
            json={
                "dryingTime": None,
                "mealTicketName": "",
                "status": "",
                "pageNum": 1,
                "delFlag": 0,
                "pageSize": 10,
                "merchantId": "2021040701",
            },
            headers={"token": self.token},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_operate_specialoffer(self):
        """
        优惠活动
        """
        payload = {
            "pageNum": 1,
            "pageSize": 10,
            "delFlag": 0,
            "merchantId": "2021040701",
            "activityName": "",
        }

        self.s.get(
            "/api/activity/performActivityList",
            params=payload,
            headers={"token": self.token},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_operate_specialactivitieStatistics(self):
        """
        优惠活动统计
        """
        payload = {
            "orderStartDate": "",
            "orderEndDate": "",
            "merchantId": "2021040701",
            "storeId": "",
            "activityName": "",
            "activityType": 1,
            "pageNum": 1,
            "pageSize": 10,
            "foodName": "",
            "cooperativeMerchantId": "",
        }
        self.s.get(
            "/api/activity/getActivityOrderStat",
            params=payload,
            headers={"token": self.token},
        )
        self.assertStatusCode(200)
        errCode = self.jsonpath("$.errCode", 0)
        status = self.jsonpath("$.status", index=0)
        print(f"查询结果的errCode是：{errCode}")
        print(f"查询结果的status是：{status}")
        self.assertPath("errCode", 0)

    def test_operate_mealManage(self):
        """
        报餐管理
        """
        self.s.post(
            "/api/ts/mealEnroll/queryPage",
            json={"pageNum": 1, "pageSize": 10, "merchantIds": ["2021040701"]},
            headers={"token": self.token},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_operate_verificationRecord(self):
        """
        核销记录
        """
        self.s.post(
            "/api/ts/mealEnrollUse/queryPage",
            json={
                "merchantId": "2021040701",
                "sysId": "iom",
                "departmentId": None,
                "storeIds": [],
                "pageNum": 1,
                "delFlag": 0,
                "pageSize": 10,
                "name": "",
                "employeeName": "",
                "employeeCode": "",
                "phoneNumber": "",
                "startDate": "",
                "endDate": "",
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
