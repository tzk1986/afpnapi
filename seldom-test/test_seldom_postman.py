"""
基于 Seldom 框架的 Postman API 测试 - 测试用例
"""

import unittest
import os
import sys
from seldom_postman_tester import PostmanApiParser, SeldomPostmanTest


class TestSeldomPostman(unittest.TestCase):
    """测试 Seldom Postman 功能"""

    def setUp(self):
        """测试前准备"""
        # 使用示例文件路径
        current_dir = os.path.dirname(os.path.abspath(__file__))
        self.test_file = os.path.join(current_dir, '..', 'sample_api_collection.json')

    def test_parser_load_file(self):
        """测试文件加载"""
        if os.path.exists(self.test_file):
            parser = PostmanApiParser(self.test_file)
            self.assertIsNotNone(parser.data)
        else:
            self.skipTest("测试文件不存在")

    def test_parser_extract_base_url(self):
        """测试基础URL提取"""
        if os.path.exists(self.test_file):
            parser = PostmanApiParser(self.test_file)
            base_url = parser.extract_base_url()
            self.assertIsInstance(base_url, str)
        else:
            self.skipTest("测试文件不存在")

    def test_parser_extract_apis(self):
        """测试API列表提取"""
        if os.path.exists(self.test_file):
            parser = PostmanApiParser(self.test_file)
            apis = parser.extract_apis()
            self.assertIsInstance(apis, list)
            if apis:
                self.assertIn('name', apis[0])
                self.assertIn('method', apis[0])
        else:
            self.skipTest("测试文件不存在")

    def test_api_test_class(self):
        """测试API测试类"""
        if os.path.exists(self.test_file):
            parser = PostmanApiParser(self.test_file)
            apis = parser.extract_apis()

            if apis:
                # 创建测试实例
                test_instance = SeldomPostmanTest(apis[0])
                self.assertIsNotNone(test_instance.api_config)
                self.assertEqual(test_instance.api_config['name'], apis[0]['name'])
        else:
            self.skipTest("测试文件不存在")


if __name__ == '__main__':
    unittest.main()