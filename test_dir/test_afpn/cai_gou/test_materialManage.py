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

    def test_materialManage_measureUnit(self):
        """
        物料管理-物料分类
        """
        tt = self.jsonpath("$..token", index=0)
        print(tt)
        payload = {"parentMcId": 0}
        self.s.get(
            "/api/mat/materialCategory/queryAll",
            params=payload,
            headers={"token": tt},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_materialManage_materialBrand(self):
        """
        物料管理-物料品牌
        """
        tt = self.jsonpath("$..token", index=0)
        print(tt)
        plaload = {"pageNum": 1, "ageSize": 10}
        self.s.get(
            "/api/mat/materialBrand/queryMaterialBrandList",
            params = plaload,
            headers={"token": tt},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_materialManage_spuManage(self):
        """
        物料管理-SPU管理
        """
        tt = self.jsonpath("$..token", index=0)
        print(tt)
        self.s.post(
            "/api/mat/materialspu/queryPage",
            json={"pageNum": 1, "pageSize": 10},
            headers={"token": tt},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_materialManage_materialRecord(self):
        """
        物料管理-物料档案
        """
        tt = self.jsonpath("$..token", index=0)
        print(tt)
        plaload = {"pageNum": 1, "ageSize": 10, "matCode": "", "matName": ""}
        self.s.get(
            "/api/mat/material/queryMaterialList",
            params=plaload,
            headers={"token": tt},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_materialManage_directSendMaterial(self):
        """
        物料管理-直送物料
        """
        tt = self.jsonpath("$..token", index=0)
        print(tt)
        plaload = {
            "pageNum": 1,
            "pageSize": 10,
            "matCode": "",
            "matName": "",
            "supplierId": "",
            "storeId": "3782d4a940e13412e301ef0a8c6ac9dd",
            "merchantId": "2021040701",
        }
        self.s.get(
            "/api/mat/materialSupplySource/queryMaterialDirectDeliveryList",
            params=plaload,
            headers={"token": tt},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_materialManage_commonUseMaterial(self):
        """
        物料管理-常用物料
        """
        tt = self.jsonpath("$..token", index=0)
        print(tt)
        self.s.post(
            "/api/wms/materialCommon/queryPage",
            json={
                "pageNum": 1,
                "pageSize": 10,
                "matCode": "",
                "matName": "",
                "storeId": "3782d4a940e13412e301ef0a8c6ac9dd",
                "merchantId": "2021040701",
            },
            headers={"token": tt},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)    


if __name__ == "__main__":
    seldom.main(
        # debug=True,
        base_url="http://10.50.11.120:9005"
    )   
