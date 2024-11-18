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

    def test_basicData_measureUnit(self):
        """
        基础数据-计量单位
        """
        tt = self.jsonpath("$..token", index=0)
        print(tt)
        self.s.post(
            "/api/base/unit/pageQuery",
            json={"pageNum": 1, "pageSize": 10, "unitName": ""},
            headers={"token": tt},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_basicData_supplierList(self):
        """
        基础数据-供应商
        """
        tt = self.jsonpath("$..token", index=0)
        print(tt)
        self.s.post(
            "/api/base/supplier/querySupplierPage",
            json={"pageNum": 1, "pageSize": 10, "supplierCode": "", "supplierName": ""},
            headers={"token": tt},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_basicData_merchant(self):
        """
        基础数据-商户配置
        """
        tt = self.jsonpath("$..token", index=0)
        print(tt)
        self.s.post(
            "/api/sys/config/queryConfig",
            json={
                "modelCode": "merchant_config",
                "configType": 2,
                "configRelationId": "2021040701",
            },
            headers={"token": tt},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_basicData_store(self):
        """
        基础数据-档口配置
        """
        tt = self.jsonpath("$..token", index=0)
        print(tt)
        self.s.post(
            "/api/sys/config/queryConfig",
            json={
                "modelCode": "store_config",
                "configType": 3,
                "configRelationId": "3782d4a940e13412e301ef0a8c6ac9dd",
            },
            headers={"token": tt},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_basicData_accountManage(self):
        """
        基础数据-计量单位
        """
        tt = self.jsonpath("$..token", index=0)
        print(tt)
        self.s.post(
            "/api/uims/user/queryPage",
            json={
                "pageNum": 1,
                "pageSize": 10,
                "organizationEntityId": "2021040701",
                "organizationType": 22,
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
