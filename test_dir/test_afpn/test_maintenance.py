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

    def test_maintenance_account(self):
        """
        账号管理
        """
        self.s.post(
            "/api/uims/user/queryPage",
            json={"pageNum": 1, "pageSize": 10, "userName": "", "phoneNumber": ""},
            headers={"token": self.token},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_maintenance_role(self):
        """
        角色管理
        """
        self.s.post(
            "/api/uims/role/queryPage",
            json={"pageNum": 1, "pageSize": 10, "name": ""},
            headers={"token": self.token},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_maintenance_admincard(self):
        """
        管理员卡
        """
        self.s.post(
            "/api/mer/machinemanagementcard/query/example",
            json={
                "delFlag": 0,
                "pageNum": 1,
                "pageSize": 10,
                "merchantId": "2021040701",
            },
            headers={"token": self.token},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_maintenance_group(self):
        """
        档口分组
        """
        self.s.post(
            "/api/mer/tree/group/next/one",
            json={
                "parentId": "0",
                "type": 0,
                "present": 1,
                "pageNum": 1,
                "delFlag": 0,
                "pageSize": 10,
                "merchantId": "2021040701",
            },
            headers={"token": self.token},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_maintenance_list(self):
        """
        档口列表
        """
        self.s.post(
            "/api/mer/store/queryPageExample/two",
            json={"pageNum": 1, "pageSize": 8, "merchantId": "2021040701"},
            headers={"token": self.token},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_maintenance_equipment(self):
        """
        设备管理
        """
        self.s.post(
            "/api/mer/machine/queryPageExampleList",
            json={
                "pageNum": 1,
                "pageSize": 10,
                "sysId": "iom",
                "merchantId": "2021040701",
                "machineType": "",
                "modelId": None,
                "status": None,
            },
            headers={"token": self.token},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_maintenance_tray(self):
        """
        托盘管理
        """
        self.s.post(
            "/api/mer/repast/queryPageExample",
            json={
                "delFlag": 0,
                "sysId": "iom",
                "pageNum": 1,
                "pageSize": 10,
                "merchantId": "2021040701",
            },
            headers={"token": self.token},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_maintenance_printer(self):
        """
        打印机管理
        """
        self.s.post(
            "/api/mer/machineprint/queryPage",
            json={
                "sysId": "iom",
                "pageNum": 1,
                "pageSize": 10,
                "delFlag": 0,
                "merchantId": "2021040701",
                "printMachineCode": "",
            },
            headers={"token": self.token},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_maintenance_deliverer(self):
        """
        配送员管理
        """
        self.s.post(
            "/api/mer/orderDeliverer/queryPage",
            json={
                "areaName": None,
                "pageNum": 1,
                "pageSize": 10,
                "merchantId": "2021040701",
            },
            headers={"token": self.token},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_maintenance_diningArea(self):
        """
        就餐区域
        """
        self.s.post(
            "/api/mer/merMerchantArea/queryPage",
            json={
                "areaName": None,
                "pageNum": 1,
                "pageSize": 10,
                "merchantId": "2021040701",
            },
            headers={"token": self.token},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_maintenance_diningLocation(self):
        """
        就餐位置
        """
        self.s.post(
            "/api/mer/merchant/area/location/queryPage",
            json={
                "pageNum": 1,
                "pageSize": 10,
                "locationName": None,
                "areaId": None,
                "enableFlag": None,
                "merchantId": "2021040701",
                "downLoadType": "",
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
