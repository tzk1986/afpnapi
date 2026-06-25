"""扩展内置变量函数单元测试。

覆盖 Step A 新增的 6 个函数：hmac_sha256/md5/base64_encode/base64_decode/random_string/url_encode。
"""

import hashlib
import hmac

from postman_api_tester.utils.variable_functions import evaluate_function


class TestHmacSha256:
    """hmac_sha256 函数测试。"""

    def test_normal_input(self):
        """正常输入返回正确的十六进制签名。"""
        expected = hmac.new(b"secret", b"data", hashlib.sha256).hexdigest()
        assert evaluate_function("hmac_sha256", "data,secret") == expected

    def test_empty_data(self):
        """data 为空时返回空字符串。"""
        assert evaluate_function("hmac_sha256", ",secret") == ""

    def test_empty_key(self):
        """key 为空时返回空字符串。"""
        assert evaluate_function("hmac_sha256", "data,") == ""

    def test_both_empty(self):
        """data 和 key 均为空时返回空字符串。"""
        assert evaluate_function("hmac_sha256", ",") == ""

    def test_no_args(self):
        """无参数时返回空字符串。"""
        assert evaluate_function("hmac_sha256", "") == ""

    def test_special_characters(self):
        """特殊字符应正确处理。"""
        expected = hmac.new(b"k!@#", b"d$%^", hashlib.sha256).hexdigest()
        assert evaluate_function("hmac_sha256", "d$%^,k!@#") == expected

    def test_unicode(self):
        """Unicode 字符应正确编码为 UTF-8 后签名。"""
        expected = hmac.new("密钥".encode("utf-8"), "数据".encode("utf-8"), hashlib.sha256).hexdigest()
        assert evaluate_function("hmac_sha256", "数据,密钥") == expected

    def test_long_input(self):
        """超长输入应正确处理。"""
        data = "a" * 10000
        key = "k" * 100
        expected = hmac.new(key.encode(), data.encode(), hashlib.sha256).hexdigest()
        assert evaluate_function("hmac_sha256", f"{data},{key}") == expected


class TestMd5:
    """md5 函数测试。"""

    def test_normal_input(self):
        """正常输入返回正确的 MD5 哈希。"""
        expected = hashlib.md5(b"hello").hexdigest()
        assert evaluate_function("md5", "hello") == expected

    def test_empty_input(self):
        """空输入返回空字符串。"""
        assert evaluate_function("md5", "") == ""

    def test_special_characters(self):
        """特殊字符应正确处理。"""
        expected = hashlib.md5(b"!@#$%^&*()").hexdigest()
        assert evaluate_function("md5", "!@#$%^&*()") == expected

    def test_unicode(self):
        """Unicode 应正确编码为 UTF-8。"""
        expected = hashlib.md5("中文".encode("utf-8")).hexdigest()
        assert evaluate_function("md5", "中文") == expected

    def test_known_hash(self):
        """已知哈希值验证。"""
        assert evaluate_function("md5", "test") == "098f6bcd4621d373cade4e832627b4f6"


class TestBase64Encode:
    """base64_encode 函数测试。"""

    def test_normal_input(self):
        """正常输入返回正确的 Base64 编码。"""
        assert evaluate_function("base64_encode", "hello") == "aGVsbG8="

    def test_empty_input(self):
        """空输入返回空字符串。"""
        assert evaluate_function("base64_encode", "") == ""

    def test_user_pass(self):
        """user:pass 格式应正确编码。"""
        assert evaluate_function("base64_encode", "user:pass") == "dXNlcjpwYXNz"

    def test_unicode(self):
        """Unicode 应正确编码。"""
        import base64
        expected = base64.b64encode("中文".encode("utf-8")).decode("utf-8")
        assert evaluate_function("base64_encode", "中文") == expected

    def test_special_chars(self):
        """特殊字符应正确处理。"""
        import base64
        expected = base64.b64encode(b"!@#$%").decode("utf-8")
        assert evaluate_function("base64_encode", "!@#$%") == expected


class TestBase64Decode:
    """base64_decode 函数测试。"""

    def test_normal_input(self):
        """正常输入返回正确的解码结果。"""
        assert evaluate_function("base64_decode", "aGVsbG8=") == "hello"

    def test_empty_input(self):
        """空输入返回空字符串。"""
        assert evaluate_function("base64_decode", "") == ""

    def test_user_pass(self):
        """user:pass 格式应正确解码。"""
        assert evaluate_function("base64_decode", "dXNlcjpwYXNz") == "user:pass"

    def test_invalid_base64(self):
        """无效 Base64 返回空字符串。"""
        assert evaluate_function("base64_decode", "!!!invalid!!!") == ""

    def test_roundtrip(self):
        """编码后解码应恢复原文。"""
        original = "test_data_123"
        encoded = evaluate_function("base64_encode", original)
        decoded = evaluate_function("base64_decode", encoded)
        assert decoded == original


class TestRandomString:
    """random_string 函数测试。"""

    def test_default_length(self):
        """默认长度为 8。"""
        result = evaluate_function("random_string", "")
        assert len(result) == 8

    def test_custom_length(self):
        """自定义长度。"""
        result = evaluate_function("random_string", "16")
        assert len(result) == 16

    def test_alpha_charset(self):
        """alpha 字符集仅包含字母。"""
        result = evaluate_function("random_string", "100,alpha")
        assert result.isalpha()

    def test_numeric_charset(self):
        """numeric 字符集仅包含数字。"""
        result = evaluate_function("random_string", "100,numeric")
        assert result.isdigit()

    def test_hex_charset(self):
        """hex 字符集仅包含十六进制字符。"""
        result = evaluate_function("random_string", "100,hex")
        assert all(c in "0123456789abcdef" for c in result)

    def test_alphanumeric_default(self):
        """默认 alphanumeric 字符集包含字母和数字。"""
        result = evaluate_function("random_string", "200")
        assert result.isalnum()

    def test_unknown_charset_fallback(self):
        """未知字符集回退到 alphanumeric。"""
        result = evaluate_function("random_string", "100,unknown_charset")
        assert result.isalnum()

    def test_zero_length(self):
        """长度为 0 返回空字符串。"""
        assert evaluate_function("random_string", "0") == ""

    def test_negative_length(self):
        """负数长度返回空字符串。"""
        assert evaluate_function("random_string", "-5") == ""

    def test_invalid_length(self):
        """非数字长度返回空字符串。"""
        assert evaluate_function("random_string", "abc") == ""

    def test_randomness(self):
        """多次调用应返回不同结果。"""
        results = {evaluate_function("random_string", "32") for _ in range(10)}
        assert len(results) > 1


class TestUrlEncode:
    """url_encode 函数测试。"""

    def test_space(self):
        """空格应编码为 %20。"""
        assert evaluate_function("url_encode", "hello world") == "hello%20world"

    def test_empty_input(self):
        """空输入返回空字符串。"""
        assert evaluate_function("url_encode", "") == ""

    def test_special_characters(self):
        """特殊字符应正确编码。"""
        result = evaluate_function("url_encode", "a=b&c=d")
        assert result == "a%3Db%26c%3Dd"

    def test_chinese(self):
        """中文应正确编码为 UTF-8 百分比序列。"""
        result = evaluate_function("url_encode", "中文")
        assert "%" in result
        assert "中文" not in result

    def test_no_encoding_needed(self):
        """无需编码的字符原样返回。"""
        assert evaluate_function("url_encode", "hello") == "hello"

    def test_slash_encoded(self):
        """斜杠应被编码（safe=''）。"""
        result = evaluate_function("url_encode", "a/b")
        assert result == "a%2Fb"


class TestEvaluateFunctionUnknown:
    """evaluate_function 未知函数测试。"""

    def test_unknown_function_returns_none(self):
        """未知函数返回 None。"""
        assert evaluate_function("nonexistent_func", "arg") is None

    def test_known_function_returns_string(self):
        """已知函数返回字符串。"""
        result = evaluate_function("md5", "test")
        assert isinstance(result, str)
        assert len(result) == 32
