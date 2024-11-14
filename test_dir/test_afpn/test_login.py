import seldom


class TestRequest(seldom.TestCase):
    """
    http api test demo
    """
    def test_umis_login(self):
        """
        test post request
        """
        self.post('/uims/login', 
                  json={
                      "systemName": "ifood-operating-manage",
                      "authenType": 1,
                      "phoneNumber": "18930410921",
                      "password": "123456",
                      "kaptchaKey": "a694c471d22149cc961a6e755d6a463f",
                      "kaptchaCode": "5865",
                    #   "token":"AA43B73579B049A8FDDB71639F45095A"
                      })
        self.assertStatusCode(200)
        jsonpath0 = self.jsonpath("$..")
        jsonpath1 = self.jsonpath("$..errCode",index=0)
        jsonpath2 = self.jsonpath("$..data")
        jsonpath3 = self.jsonpath("$.data.userInfo.name")
        print(jsonpath0)
        print(jsonpath1)
        print(jsonpath2)
        print(jsonpath3)
        self.assertPath("data.enterpriseInfo.name", "上海艾佩菲宁")

    def test_umis_logout(self):
        """
        test get request
        """
        self.get("/uims/logout")
        self.assertStatusCode(200)
        # 断言数据
        # assert_data = {
        #     "errCode": 100001,
        #     "message": "session 已经过期.",
        #     }
        # self.assertJSON(assert_data, self.jsonpath("$.."), exclude=["xxx"])
        # assertJSON 断言   第一个参数是预期值，第二个参数是实际值，第三个参数是排除的字段
        self.assertJSON(100001, self.jsonpath("$..errCode",index=0))
        self.assertJSON("session 已经过期.", self.jsonpath("$..message",index=0))
        # assertPath 断言  第一个参数是路径，第二个参数是预期值
        self.assertPath("errCode", 100001)
        self.assertPath("message", "session 已经过期.")







if __name__ == '__main__':
    seldom.main(
                debug=True, 
                base_url="http://10.50.11.120:8090"
                )