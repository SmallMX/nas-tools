import base64

from app.utils import RequestUtils
from config import Config


class OcrHelper:
    req = None

    def __init__(self):
        self.req = RequestUtils(content_type="application/json")

    def get_captcha_text(self, image_url=None, image_b64=None):
        """
        根据图片地址，获取验证码图片，并识别内容
        """
        ocr_server = Config().get_config('app').get('ocr_server')
        if not isinstance(ocr_server, str) or not ocr_server.strip():
            return ""
        ocr_b64_url = "%s/captcha/base64" % ocr_server.strip().rstrip('/')
        if not image_url and not image_b64:
            return ""
        if image_url:
            ret = self.req.get_res(image_url)
            if ret is not None:
                image_bin = ret.content
                if not image_bin:
                    return ""
                image_b64 = base64.b64encode(image_bin).decode()
        ret = self.req.post_res(url=ocr_b64_url,
                                json={"base64_img": image_b64})
        if ret:
            return ret.json().get("result")
        return ""
