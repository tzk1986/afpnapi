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

    def end(self):
        print("结束测试")

    def test_purchaseManage_materialApplication(self):
        """
        采购管理-物料申请单
        """
        tt = self.jsonpath("$..token", index=0)
        print(tt)
        payload = {
            "corpId": "e3b767ab3d542be199748389670ca9be",
            "pageNum": 1,
            "pageSize": 10,
            "orderCode": "",
        }
        self.s.post(
            "/api/pur/materialRequest/queryPage",
            json=payload,
            headers={"token": tt},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_purchaseManage_competition(self):
        """
        采购管理-竞价采购
        """
        tt = self.jsonpath("$..token", index=0)
        print(tt)
        payload = {"pageNum": 1, "pageSize": 10}
        self.s.post(
            "/api/pur/bidding/queryPage",
            json=payload,
            headers={"token": tt},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_purchaseManage_quotation(self):
        """
        采购管理-报价采购
        """
        tt = self.jsonpath("$..token", index=0)
        print(tt)
        payload = {"pageNum": 1, "pageSize": 10}
        self.s.post(
            "/api/pur/spu/bidding/queryPage",
            json=payload,
            headers={"token": tt},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_purchaseManage_purchaseOrder(self):
        """
        采购管理-采购订单
        """
        tt = self.jsonpath("$..token", index=0)
        print(tt)
        payload = {"pageNum": 1, "pageSize": 10}
        self.s.post(
            "/api/pur/purchase/order/queryPage",
            json=payload,
            headers={"token": tt},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_purchaseManage_purchasePrincipal(self):
        """
        采购管理-结算主体
        """
        tt = self.jsonpath("$..token", index=0)
        print(tt)
        payload = {
            "pageNum": 1,
            "pageSize": 10,
            "settleOrgName": "",
            "settleOrgCode": "",
        }
        self.s.post(
            "/api/base/settlement/org/pageQuery",
            json=payload,
            headers={"token": tt},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)


if __name__ == "__main__":
    seldom.main(
        # debug=True,
        base_url="http://10.50.11.120:9005"
    )   
