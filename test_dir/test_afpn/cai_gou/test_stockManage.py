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

    def test_stockManage_inboundAcceptance(self):
        """
        库存管理-验收管理
        """
        tt = self.jsonpath("$..token", index=0)
        print(tt)
        payload = {
            "pageNum": 1,
            "pageSize": 10,
            "purchaseOrderCode": "",
            "deliverOrderCode": "",
        }
        self.s.post(
            "/api/pur/deliverOrder/queryPage",
            json=payload,
            headers={"token": tt},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_stockManage_outboundPickOut(self):
        """
        库存管理-领用管理
        """
        tt = self.jsonpath("$..token", index=0)
        print(tt)
        payload = {"pageNum": 1, "pageSize": 10, "orderCode": ""}
        self.s.post(
            "/api/takeout/order/queryPage",
            json=payload,
            headers={"token": tt},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_stockManage_inboundReceipt(self):
        """
        库存管理-入库单
        """
        tt = self.jsonpath("$..token", index=0)
        print(tt)
        payload = {
            "pageNum": 1,
            "pageSize": 10,
            "orderCode": "",
            "inboundOrderCode": "",
            "deliveryOrderCode": "",
            "inboundDateBegin": "2024-10-19",
            "inboundDateEnd": "2024-11-18",
        }

        self.s.get(
            "/api/wms/inboundOrder/queryInBoundOrderList",
            params=payload,
            headers={"token": tt},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_stockManage_outboundReceipt(self):
        """
        库存管理-出库单
        """
        tt = self.jsonpath("$..token", index=0)
        print(tt)
        payload = {
            "pageNum": 1,
            "pageSize": 10,
            "outboundOrderCode": "",
            "takeOutOrderCode": "",
            "outboundDateBegin": "2024-10-19",
            "outboundDateEnd": "2024-11-18",
        }

        self.s.get(
            "/api/wms/outboundOrder/queryOutboundOrderList",
            params=payload,
            headers={"token": tt},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_stockManage_stockSearch(self):
        """
        库存管理-库存查询
        """
        tt = self.jsonpath("$..token", index=0)
        print(tt)
        payload = {
            "pageNum": 1,
            "pageSize": 10,
            "matCode": "",
            "matName": "",
            "brandId": "",
        }

        self.s.get(
            "/api/wms/stockSummary/queryStockSummaryList",
            params=payload,
            headers={"token": tt},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_stockManage_stockJournalizing(self):
        """
        库存管理-库存流水查询
        """
        tt = self.jsonpath("$..token", index=0)
        print(tt)
        payload = {
            "pageNum": 1,
            "pageSize": 10,
            "matCode": "",
            "matName": "",
            "brandId": "",
            "duplexBoundDateBegin": "2024-10-19",
            "duplexBoundDateEnd": "2024-11-18",
        }

        self.s.get(
            "/api/wms/stockFlow/queryStockFlowList",
            params=payload,
            headers={"token": tt},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_stockManage_alertConfig(self):
        """
        库存管理-预警配置
        """
        tt = self.jsonpath("$..token", index=0)
        print(tt)
        payload = {"pageNum": 1, "pageSize": 10, "matCode": "", "matName": ""}
        self.s.get(
            "/api/wms/stockWarningConfig/queryStockWarningList",
            params=payload,
            headers={"token": tt},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_stockManage_wareHouse(self):
        """
        库存管理-仓库
        """
        tt = self.jsonpath("$..token", index=0)
        print(tt)
        payload = {
            "corpId": "e3b767ab3d542be199748389670ca9be",
            "name": "",
            "storeId": "",
            "code": "",
            "type": 1,
            "pageNum": 1,
            "pageSize": 10,
        }
        self.s.post(
            "/api/wms/warehouse/queryPage",
            json=payload,
            headers={"token": tt},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_stockManage_distributionSite(self):
        """
        库存管理-配送点
        """
        tt = self.jsonpath("$..token", index=0)
        print(tt)
        payload = {
            "corpId": "e3b767ab3d542be199748389670ca9be",
            "storeId": "",
            "deliverAddrCode": "",
            "deliverAddrName": "",
            "address": "",
            "warehouseName": "",
            "pageNum": 1,
            "pageSize": 10,
        }
        self.s.post(
            "/api/wms/warehouse/deliverAddress/queryPage",
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
