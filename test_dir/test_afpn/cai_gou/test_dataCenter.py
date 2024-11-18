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

    def test_dataCenter_importedFiles(self):
        """
        导入导出-导入管理
        """
        tt = self.jsonpath("$..token", index=0)
        print(tt)
        payload = {"pageNum": 1, "pageSize": 10, "sysId": "scm"}
        self.s.post(
            "/api/import/query",
            json=payload,
            headers={"token": tt},
        )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)

    def test_dataCenter_exportedFiles(self):
        """
        导入导出-导出管理
        """
        tt = self.jsonpath("$..token", index=0)
        print(tt)
        payload = {"pageNum": 1, "pageSize": 10, "sysId": "scm"}
        self.s.post(
            "/api/export/query",
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
