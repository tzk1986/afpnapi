import seldom


class TestRequest(seldom.TestCase):
    """
    前厅食安页面
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

    def test_data_dishsale(self):
        """
        菜品销售数据
        """
        tt = self.jsonpath("$..token", index=0)
        print(tt)
        self.s.post(
            "/api/orderdetail/ts/orderDetail/dishAggPage",
            json={
                "sysId": "iom",
                "merchantId": "2021040701",
                "storeId": None,
                "categoryName": None,
                "foodName": None,
                "dataType": 1,
                "sumType": 1,
                "orderOriginal": 1,
                "weighType": None,
                "startDate": "2024-11-13T16:00:00.000Z",
                "endDate": "2024-11-14T15:59:59.999Z",
                "sortProp": None,
                "sortRule": None,
                "pageNum": 1,
                "pageSize": 10,
            },
            headers={"token": tt},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_data_dishrefund(self):
        """
        菜品退款数据
        """
        tt = self.jsonpath("$..token", index=0)
        print(tt)
        self.s.post(
            "/api/orderdetail/ts/orderDetail/dishAggPage",
            json={
                "sysId": "iom",
                "merchantId": "2021040701",
                "storeId": None,
                "categoryName": None,
                "foodName": None,
                "dataType": 2,
                "sumType": 1,
                "orderOriginal": 1,
                "weighType": None,
                "sortProp": None,
                "sortRule": None,
                "startDate": "2024-11-13T16:00:00.000Z",
                "endDate": "2024-11-14T15:59:59.999Z",
                "pageNum": 1,
                "pageSize": 10,
            },
            headers={"token": tt},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_data_dishsum(self):
        """
        菜品汇总统计
        """
        tt = self.jsonpath("$..token", index=0)
        print(tt)
        self.s.post(
            "/api/order/dish/agg/findCollectList",
            json={
                "pageNum": 1,
                "pageSize": 10,
                "queryType": "date",
                "merchantId": "2021040701",
                "storeIds": [],
                "startDate": "2024-10-15",
                "endDate": "2024-11-15",
            },
            headers={"token": tt},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_data_dishpickup(self):
        """
        预定取餐统计
        """
        tt = self.jsonpath("$..token", index=0)
        print(tt)
        self.s.post(
            "/api/reserve/dishAgg/queryPage",
            json={
                "pageNum": 1,
                "pageSize": 10,
                "storeIds": [],
                "merchantId": "2021040701",
                "foodName": None,
                "startDate": "2024-11-13T16:00:00.000Z",
                "endDate": "2024-11-14T15:59:59.999Z",
            },
            headers={"token": tt},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_data_cooking(self):
        """
        炒菜机烹饪数据
        """
        tt = self.jsonpath("$..token", index=0)
        print(tt)
        self.s.post(
            "/api/stir/menu/burn/record/queryPage",
            json={
                "sumType": 1,
                "storeId": "",
                "recordType": 1,
                "recipeName": "",
                "machineName": "",
                "startTime": "2024-11-13T16:00:00.000Z",
                "endTime": "2024-11-14T15:59:59.999Z",
                "merchantId": "2021040701",
                "pageNum": 1,
                "sortProp": None,
                "sortRule": None,
                "delFlag": 0,
                "pageSize": 10,
                "sysId": "iom",
            },
            headers={"token": tt},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_data_running(self):
        """
        炒菜机运行数据
        """
        tt = self.jsonpath("$..token", index=0)
        print(tt)
        self.s.post(
            "/api/stir/merchant/burn/recipe/queryPage",
            json={
                "sysId": "iom",
                "pageNum": 1,
                "delFlag": 0,
                "pageSize": 10,
                "recordType": 1,
                "sumType": 1,
                "storeId": "",
                "recipeName": "",
                "querySource": "",
                "recipeType": "",
                "machineName": "",
                "status": None,
                "dateFrom": "2024-11-13T16:00:00.000Z",
                "dateTo": "2024-11-14T15:59:59.999Z",
                "merchantId": "2021040701",
            },
            headers={"token": tt},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_data_roastcooking(self):
        """
        蒸烤箱烹饪数据
        """
        tt = self.jsonpath("$..token", index=0)
        print(tt)
        self.s.post(
            "/api/stir/menu/burn/record/queryPage",
            json={
                "sumType": 1,
                "storeId": "",
                "recordType": 2,
                "recipeName": "",
                "machineName": "",
                "sortProp": None,
                "sortRule": None,
                "startTime": "2024-11-13T16:00:00.000Z",
                "endTime": "2024-11-14T15:59:59.999Z",
                "merchantId": "2021040701",
                "pageNum": 1,
                "delFlag": 0,
                "pageSize": 10,
                "sysId": "iom",
            },
            headers={"token": tt},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_data_roastrunning(self):
        """
        蒸烤箱运行数据
        """
        tt = self.jsonpath("$..token", index=0)
        print(tt)
        self.s.post(
            "/api/stir/roast/cook/record/queryPage",
            json={
                "sumType": 1,
                "storeId": "",
                "recipeName": "",
                "recipeType": "",
                "machineName": "",
                "status": None,
                "dateFrom": "2024-11-13T16:00:00.000Z",
                "dateTo": "2024-11-14T15:59:59.999Z",
                "merchantId": "2021040701",
                "pageNum": 1,
                "delFlag": 0,
                "pageSize": 10,
                "sysId": "iom",
            },
            headers={"token": tt},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_data_consumedataana(self):
        """
        消费数据分析
        """
        tt = self.jsonpath("$..token", index=0)
        print(tt)
        self.s.post(
            "/api/orderdetail/ts/consumption/data/analysis",
            json={
                "sysId": "iom",
                "merchantId": "2021040701",
                "phoneNumber": None,
                "nickName": None,
                "employeeCode": None,
                "employeeName": None,
                "enterpriseId": "2021040701",
                "departmentId": None,
                "positionId": None,
                "dataType": 1,
                "sumType": 1,
                "orderOriginal": 1,
                "sortProp": None,
                "sortRule": None,
                "pageNum": 1,
                "pageSize": 10,
            },
            headers={"token": tt},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_data_behavioraldata(self):
        """
        行为数据
        """
        tt = self.jsonpath("$..token", index=0)
        print(tt)
        self.s.post(
            "/api/mer/camera/queryWarningPage",
            json={
                "pageNum": 1,
                "pageSize": 18,
                "merchantId": "2021040701",
                "machineType": 7,
                "startDate": "2024-11-14T16:00:00.000Z",
                "endDate": "2024-11-15T15:59:59.999Z",
                "machineId": "2696331985ff5723fa27a30b7981eec2",
            },
            headers={"token": tt},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_data_weighingmachinerecipe(self):
        """
        称重机菜品
        """
        tt = self.jsonpath("$..token", index=0)
        print(tt)
        self.s.post(
            "/api/mer/machinegoodconfig/queryMachineGoodPage",
            json={
                "pageNum": 1,
                "pageSize": 10,
                "storeId": None,
                "merchantId": "2021040701",
            },
            headers={"token": tt},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_data_businessbigdata(self):
        """
        智慧经营大数据
        """
        tt = self.jsonpath("$..token", index=0)
        print(tt)
        self.s.post(
            "/api/dw/app/data/iom/bulk",
            json={
                "queries": [
                    {
                        "dataset": "meal_type_amount_and_count",
                        "param": {"merchantId": "2021040701"},
                    }
                ]
            },
            headers={"token": tt},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_data_lobbyData(self):
        """
        前厅数据可视化
        """
        tt = self.jsonpath("$..token", index=0)
        print(tt)
        self.s.post(
            "/api/dw/app/data/iom/bulk",
            json={
                "queries": [
                    {"dataset": "recent_5_deals", "param": {"merchantId": "2021040701"}}
                ]
            },
            headers={"token": tt},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_data_purchaseData(self):
        """
        采购数据可视化
        """
        tt = self.jsonpath("$..token", index=0)
        print(tt)
        self.s.post(
            "/api/dw/app/data/iom/bulk",
            json={
                "queries": [
                    {
                        "dataset": "pur_goods_out_order_tendency",
                        "param": {"merchantId": "2021040701"},
                    }
                ]
            },
            headers={"token": tt},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_data_smartkitchen(self):
        """
        智慧后厨可视化
        """
        tt = self.jsonpath("$..token", index=0)
        print(tt)
        self.s.post(
            "/api/dw/app/data/iom/bulk",
            json={
                "queries": [
                    {"dataset": "food_consume", "param": {"merchantId": "2021040701"}}
                ]
            },
            headers={"token": tt},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_data_importfile(self):
        """
        导入文件
        """
        tt = self.jsonpath("$..token", index=0)
        print(tt)
        self.s.post(
            "/api/import/query",
            json={
                "merchantId": None,
                "importDate": None,
                "sysId": "iom",
                "userId": "4951d48c3fa68e4ac8197de6cfd7de0f",
                "pageNum": 1,
                "delFlag": 0,
                "pageSize": 10,
            },
            headers={"token": tt},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_data_exportfile(self):
        """
        导出文件
        """
        tt = self.jsonpath("$..token", index=0)
        print(tt)
        self.s.post(
            "/api/export/query",
            json={
                "merchantId": None,
                "exportDate": None,
                "sysId": "iom",
                "userId": "4951d48c3fa68e4ac8197de6cfd7de0f",
                "pageNum": 1,
                "delFlag": 0,
                "pageSize": 10,
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
