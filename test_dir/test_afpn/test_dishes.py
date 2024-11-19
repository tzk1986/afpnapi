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
        self.token = self.jsonpath("$..token", index=0)

    def end(self):
        print("结束测试")

    def test_dishes_spec(self):
        """
        规格
        """
        self.s.post(
            "/api/goods/specgroup/queryPage",
            json={
                "specGroupName": "",
                "merchantId": "2021040701",
                "pageNum": 1,
                "pageSize": 10,
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
            print(f"查询到的订单总数量是：{num}")
        else:
            errCode = self.jsonpath("$..errCode", index=0)
            print("查询失败")
            print(f"查询失败的错误码是：{errCode}")

    def test_dishes_flavor(self):
        """
        口味
        """
        self.s.post(
            "/api/goods/flavorgroup/queryPage",
            json={
                "flavorGroupName": "",
                "merchantId": "2021040701",
                "pageNum": 1,
                "pageSize": 10,
            },
            headers={"token": self.token},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_dishes_category(self):
        """
        分类
        """
        self.s.post(
            "/api/goods/category/queryPage",
            json={
                "sysId": "iom",
                "categoryName": "",
                "type": None,
                "pageNum": 1,
                "delFlag": 0,
                "pageSize": 10,
                "merchantId": "2021040701",
            },
            headers={"token": self.token},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_dishes_single(self):
        """
        单品菜品
        """
        self.s.post(
            "/api/goods/dish/queryPage",
            json={
                "merchantId": "2021040701",
                "categoryId": "",
                "dishName": "",
                "valuationType": "",
                "status": "",
                "pageNum": 1,
                "delFlag": 0,
                "pageSize": 10,
                "sysId": "iom",
            },
            headers={"token": self.token},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_dishes_singlecomb(self):
        """
        单品组合
        """
        self.s.post(
            "/api/goods/dish/group/queryAll",
            json={"merchantId": "2021040701"},
            headers={"token": self.token},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_dishes_combo(self):
        """
        套餐菜品
        """
        self.s.post(
            "/api/goods/combo/queryPage",
            json={
                "comboName": "",
                "valuationType": "",
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

    def test_dishes_remark(self):
        """
        菜品备注
        """
        self.s.post(
            "/api/goods/food/remark/queryPage",
            json={
                "merchantId": "2021040701",
                "remark": None,
                "id": 1,
                "pageNum": 1,
                "delFlag": 0,
                "pageSize": 10,
            },
            headers={"token": self.token},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_dishes_arrange(self):
        """
        排餐
        """
        self.s.post(
            "/api/mer/arrange/meal/queryPage",
            json={
                "pageNum": 1,
                "pageSize": 10,
                "delFlag": 0,
                "storeId": "1fda7cedd736452fb5ea6f2f1f3eae36",
                "merchantId": "2021040701",
                "startDate": "2024-11-11",
                "foodName": "",
                "valuationType": 3,
            },
            headers={"token": self.token},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_dishes_ingredientEstimate(self):
        """
        食材预估
        """
        self.s.post(
            "/api/mer/estimation/queryPage",
            json={
                "pageNum": 1,
                "pageSize": 10,
                "queryStartTime": None,
                "queryEndTime": None,
                "merchantId": "2021040701",
            },
            headers={"token": self.token},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_dishes_group(self):
        """
        菜谱分组
        """
        self.s.post(
            "/api/stir/recipe/group/queryPage",
            json={
                "name": "",
                "storeId": "",
                "type": "0",
                "pageNum": 1,
                "delFlag": 0,
                "pageSize": 10,
                "merchantId": "2021040701",
            },
            headers={"token": self.token},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_dishes_typerecipe(self):
        """
        菜谱分类
        """
        self.s.post(
            "/api/stir/recipe/type/queryPage",
            json={
                "name": "",
                "storeId": "",
                "type": 0,
                "pageNum": 1,
                "delFlag": 0,
                "pageSize": 10,
            },
            headers={"token": self.token},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_dishes_material(self):
        """
        原料管理
        """
        self.s.post(
            "/api/stir/ingredients/queryPage",
            json={"pageNum": 1, "pageSize": 10, "delFlag": 0, "name": "", "type": 1},
            headers={"token": self.token},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_dishes_kitchenflavour(self):
        """
        调料管理
        """
        self.s.post(
            "/api/stir/seasoning/queryPage",
            json={"pageNum": 1, "pageSize": 10, "delFlag": 0, "name": "", "type": 1},
            headers={"token": self.token},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_dishes_platformMenu(self):
        """
        平台菜谱
        """
        self.s.post(
            "/api/stir/recipe/base/queryRecipeBasePage",
            json={
                "pageNum": 1,
                "pageSize": 10,
                "delFlag": 0,
                "orgTypeSet": [1],
                "sourceType": 1,
                "recipeBaseName": "",
                "recipeMachineType": 1,
            },
            headers={"token": self.token},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_dishes_selfstudyMenu(self):
        """
        自研菜谱
        """
        self.s.post(
            "/api/stir/recipe/base/queryRecipeBasePage",
            json={
                "pageNum": 1,
                "pageSize": 10,
                "delFlag": 0,
                "orgTypeSet": [],
                "corporationId": "e3b767ab3d542be199748389670ca9be",
                "sourceType": 0,
                "recipeBaseName": "",
                "recipeMachineType": 1,
            },
            headers={"token": self.token},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_dishes_menuLicense(self):
        """
        菜谱授权
        """
        self.s.post(
            "/api/stir/recipe/base/queryRecipeBasePage",
            json={
                "onlySelf": 1,
                "queryOrgType": None,
                "pubFlag": 0,
                "sourceType": 0,
                "pageNum": 1,
                "pageSize": 10,
                "delFlag": 0,
                "recipeBaseName": "",
                "recipeGroupId": None,
                "recipeMachineType": 1,
                "lastVersionStatus": 2,
                "merchantId": "2021040701",
            },
            headers={"token": self.token},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_dishes_divideburn(self):
        """
        烧录分组
        """
        self.s.post(
            "/api/stir/burn/group/queryPage",
            json={
                "pageNum": 1,
                "pageSize": 10,
                "groupName": "",
                "groupType": "",
                "storeId": "",
            },
            headers={"token": self.token},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_dishes_issue(self):
        """
        菜谱下发
        """
        self.s.post(
            "/api/stir/recipe/burnbase/queryPage",
            json={
                "pageNum": 1,
                "pageSize": 10,
                "delFlag": 0,
                "groupName": "",
                "groupId": "",
                "burnType": "",
                "recipeGroupId": None,
                "merchantId": "2021040701",
                "baseStatus": "",
                "machineName": "",
                "machineCode": "",
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
