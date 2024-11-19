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

    def test_financeManage_supplierReconciliation(self):
        """
        财务管理-供应商对账
        """
        payload = {
            "merchantId": "2021040701",
            "date": "2024-12",
            "startTime": None,
            "endTime": None,
        }
        self.s.post(
            "/api/report/supplier/querySupplierReport",
            json=payload,
            headers={"token": self.token},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_financeManage_acceptanceStatistics(self):
        """
        财务管理-验收统计
        """
        payload = {
            "pageNum": 1,
            "pageSize": 10,
            "startTime": "2024-10-19 00:00:00",
            "endTime": "2024-11-18 23:59:59",
        }
        self.s.post(
            "/api/stat/acceptMaterialStat/acceptDayAmount",
            json=payload,
            headers={"token": self.token},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_financeManage_storeReconciliation(self):
        """
        财务管理-档口对账
        """
        payload = {"merchantId": "2021040701", "statType": "store", "month": "202412"}
        self.s.post(
            "/api/stat/outboundMaterialStat/queryOutboundMonthCost",
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
