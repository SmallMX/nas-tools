import base64
import hashlib
import json
from urllib.parse import quote

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from app.utils import RequestUtils


class CookieCloudHelper(object):
    _req = None
    _server = None
    _key = None
    _password = None

    def __init__(self, server, key, password):
        self._server = server.strip() if isinstance(server, str) else ""
        if self._server:
            if not self._server.lower().startswith(("http://", "https://")):
                self._server = "http://%s" % self._server
            self._server = self._server.rstrip("/")
        self._key = key.strip() if isinstance(key, str) else ""
        self._password = password if isinstance(password, str) else ""
        self._req = RequestUtils(content_type="application/json")

    def download_data(self):
        """
        下载并解密CookieCloud数据，返回域名到原始Cookie列表的映射及错误信息。
        """
        if not self._server or not self._key or not self._password:
            return {}, "CookieCloud参数不正确"
        req_url = "%s/get/%s" % (self._server, quote(self._key, safe=""))
        # 获取密文并在本地解密，不将加密密码发送到CookieCloud服务器。
        ret = self._req.get_res(url=req_url)
        if ret is None:
            return {}, "CookieCloud请求失败，请检查服务器地址、用户KEY及加密密码是否正确"
        try:
            if ret.status_code != 200:
                return {}, "同步CookieCloud失败，错误码：%s" % ret.status_code
            try:
                result = ret.json()
            except ValueError:
                return {}, "CookieCloud返回的数据不是有效的JSON"
        finally:
            ret.close()

        if not isinstance(result, dict):
            return {}, "CookieCloud返回的数据格式不正确"
        if "encrypted" in result:
            crypto_type = result.get("crypto_type") or "legacy"
            if crypto_type not in ("legacy", "aes-128-cbc-fixed"):
                return {}, "CookieCloud加密算法不受支持"
            try:
                result = self._decrypt_data(result["encrypted"], crypto_type)
            except (ValueError, TypeError, UnicodeError):
                return {}, "CookieCloud解密失败，请检查用户KEY、加密密码或重新上传Cookie"

        if not isinstance(result, dict):
            return {}, "CookieCloud返回的数据格式不正确"
        contents = result.get("cookie_data", result)
        if not isinstance(contents, dict) or any(
                not isinstance(domain, str) or not isinstance(cookies, list)
                or any(not isinstance(cookie, dict) for cookie in cookies)
                for domain, cookies in contents.items()):
            return {}, "CookieCloud返回的Cookie数据格式不正确"
        if not contents:
            return {}, "未从CookieCloud获取到Cookie数据"
        return contents, ""

    def _decrypt_data(self, encrypted, crypto_type):
        """兼容CookieCloud的CryptoJS legacy和AES-128-CBC加密格式。"""
        encrypted = base64.b64decode(encrypted, validate=True)
        passphrase = hashlib.md5(f"{self._key}-{self._password}".encode("utf-8")).hexdigest()[:16].encode("utf-8")
        if crypto_type == "aes-128-cbc-fixed":
            key, iv = passphrase, bytes(16)
        else:
            if len(encrypted) < 32 or not encrypted.startswith(b"Salted__"):
                raise ValueError("Invalid CryptoJS payload")
            salt, encrypted = encrypted[8:16], encrypted[16:]
            # CryptoJS使用OpenSSL EVP_BytesToKey派生32字节密钥和16字节IV。
            key_iv, previous = b"", b""
            while len(key_iv) < 48:
                previous = hashlib.md5(previous + passphrase + salt).digest()
                key_iv += previous
            key, iv = key_iv[:32], key_iv[32:48]
        decryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
        padded = decryptor.update(encrypted) + decryptor.finalize()
        unpadder = padding.PKCS7(128).unpadder()
        decrypted = unpadder.update(padded) + unpadder.finalize()
        return json.loads(decrypted.decode("utf-8"))
