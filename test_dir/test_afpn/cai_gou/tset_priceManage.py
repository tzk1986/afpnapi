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

    def test_priceManage_purchasePrice(self):
        """
        价格管理-采购价格
        """
        payload = {"pageNum": 1, "pageSize": 10}
        self.s.get(
            "/api/mat/purchasePrice/queryPurchasePriceList",
            params=payload,
            headers={"token": self.token},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_priceManage_retrievalPrice(self):
        """
        价格管理-出库价格
        """
        payload = {
            "pageNum": 1,
            "pageSize": 10,
            "mcId": "",
            "matCode": "",
            "matName": "",
            "brandId": "",
            "startDate": "",
            "endDate": "",
        }
        self.s.get(
            "/api/mat/outboundPrice/queryOutboundPriceList",
            params=payload,
            headers={"token": self.token},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_priceManage_adjustPrice(self):
        """
        价格管理-调价管理
        """
        payload = {"pageNum": 1, "pageSize": 10}
        self.s.post(
            "/api/mat/purchasePriceChangeRequest/queryChangePriceRequestList",
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
