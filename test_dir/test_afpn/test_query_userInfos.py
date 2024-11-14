import seldom


class TestRequest(seldom.TestCase):
    """
    查配置列表
    """
    def start(self):
        self.s = self.Session()
        self.s.post('/api/uims/login', 
                  json={
                      "systemName": "ifood-operating-manage",
                      "authenType": 1,
                      "password": "123456",
                      "phoneNumber": "18930410921",
                      "smsCode": "",
                      "kaptchaCode": "1",
                      "kaptchaKey": "65eb74b59e224db1b8f6ba3266848380"
                      })
        self.assertStatusCode(200)
        print(self.s)
        
        
    def test_query_userInfos(self):
        """
        会员列表查询
        """
        tt = self.jsonpath("$..token",index=0)
        print(tt)
        self.post("/api/query/userInfos",
                 json={"userBackStatus":"0","phoneNumber":"","nickName":"","memberCard":"","merchantId":"2021040701","pageNum":1,"delFlag":0,"pageSize":10,"sysId":"iom"},
                 headers={"token":tt}
                 )
        self.assertStatusCode(200)
        self.assertPath("errCode", 0)
        self.assertPath("data.list[1].merchantName", "上海艾佩菲宁")






if __name__ == '__main__':
    seldom.main(
                debug=True, 
                base_url="http://10.50.11.120:9001"
                )