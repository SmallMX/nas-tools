import requests

from config import Config


class RequestUtils:
    """
    网络请求工具类，封装了 HTTP 请求（GET/POST 等），方便项目各处复用。
    对于 Python 初学者，可以把这个类看作是一个“专门负责发网络请求的服务员”。
    主要功能包括：
    1. 统一管理请求头 (Headers)、Cookie、代理 (Proxies)
    2. 支持保持会话 (Session，可以让多个请求共享登录状态)
    3. 统一处理网络错误，捕获异常以防止抛出异常导致整个程序崩溃退出
    """
    
    # 类的属性，定义了请求时默认的一些参数
    _headers = None     # 请求头，包含 User-Agent 等信息，告诉服务器我们是什么浏览器
    _cookies = None     # 请求携带的 Cookie，用于身份认证和维持登录
    _proxies = None     # 代理设置，当需要科学上网请求外部 API 时使用
    _timeout = 20       # 请求超时时间，如果 20 秒服务器没响应就放弃，防止程序死等
    _session = None     # 会话对象，如果提供则使用该 Session 进行连续请求
    _verify = True      # 默认验证 HTTPS 证书；自签名服务必须由调用方显式传入 CA 或关闭验证

    def __init__(self,
                 headers=None,
                 cookies=None,
                 proxies=False,
                 session=None,
                 timeout=None,
                 referer=None,
                 content_type=None,
                 verify=True):
        """
        初始化方法（也就是构造函数），在创建 RequestUtils 工具对象时会被调用。
        可以在这里把我们需要的配置传进来。
        
        参数说明：
        :param headers: 请求头，可以是字典；如果是字符串则会被自动作为 User-Agent 处理
        :param cookies: Cookie，支持字符串格式（会自动解析）或字典格式
        :param proxies: 代理配置字典，如 {"http": "...", "https": "..."}
        :param session: requests.Session 对象，用于维持长连接和登录会话
        :param timeout: 超时时间，单位秒
        :param referer: HTTP Referer，告诉目标服务器我们是从哪个页面跳转过来的
        :param content_type: 请求数据类型，如 application/json 等
        """
        # 如果未指定 content_type，默认为表单提交类型，并且指定编码为 UTF-8
        if not content_type:
            content_type = "application/x-www-form-urlencoded; charset=UTF-8"
            
        # 处理传入的 headers（请求头）
        if headers:
            # isinstance() 用于判断 headers 是否是字符串类型
            if isinstance(headers, str):
                self._headers = {
                    "Content-Type": content_type,
                    "User-Agent": f"{headers}"
                }
            else:
                self._headers = dict(headers)
        else:
            # 如果没有传入 headers，则使用全局配置文件 (Config) 中默认的 User-Agent
            self._headers = {
                "Content-Type": content_type,
                "User-Agent": Config().get_ua()
            }
            
        # 如果指定了 referer，将其添加到请求头字典中
        if referer:
            self._headers.update({
                "referer": referer
            })
            
        # 处理传入的 cookies
        self._cookies = None
        if cookies:
            if isinstance(cookies, str):
                # 如果 cookie 是字符串（如从浏览器F12直接复制的），调用 cookie_parse 自动将其解析为字典
                self._cookies = self.cookie_parse(cookies)
            else:
                self._cookies = cookies
                
        # 每个实例都显式初始化，避免复用类属性造成状态串扰
        self._proxies = proxies or None
        self._session = session
        self._timeout = timeout or 20
        self._verify = verify

    def post(self, url, params=None, json=None):
        """
        发送 POST 请求的方法。
        通常用于向服务器提交数据。
        :param url: 请求的目标网址
        :param params: 表单数据字典 (对应 requests 中的 data 参数)
        :param json: JSON 格式的字典数据
        :return: requests.Response 响应对象，如果遇到网络异常则安全地返回 None
        """
        # try...except... 结构用于异常捕获。如果里面的代码出错，会被 except 抓住，而不会让程序直接崩掉
        try:
            if self._session:
                # 使用 session 发送请求
                return self._session.post(url,
                                          data=params,      # 表单数据
                                          verify=self._verify,
                                          headers=self._headers,
                                          proxies=self._proxies,
                                          timeout=self._timeout,
                                          json=json)        # JSON 数据
            else:
                # 使用普通的 requests.post 发送一次性请求
                return requests.post(url,
                                     data=params,
                                     verify=self._verify,
                                     headers=self._headers,
                                     proxies=self._proxies,
                                     timeout=self._timeout,
                                     json=json)
        # 如果发生任何网络请求相关的异常（如断网、DNS解析失败等）
        except requests.exceptions.RequestException:
            # 静默处理，返回 None 让上层代码去判断
            return None

    def get(self, url, params=None):
        """
        发送 GET 请求，并按响应编码返回字符串内容。
        通常用于获取网页 HTML 或 API 返回的文本数据。
        
        :param url: 请求地址
        :param params: URL 查询参数 (附加在 URL 末尾的参数，如 ?a=1&b=2)
        :return: 网页的字符串文本内容，如果发生网络异常则返回 None
        """
        try:
            if self._session:
                r = self._session.get(url,
                                      verify=self._verify,
                                      headers=self._headers,
                                      proxies=self._proxies,
                                      cookies=self._cookies,
                                      timeout=self._timeout,
                                      params=params)
            else:
                r = requests.get(url,
                                 verify=self._verify,
                                 headers=self._headers,
                                 proxies=self._proxies,
                                 cookies=self._cookies,
                                 timeout=self._timeout,
                                 params=params)
            return r.text
        except requests.exceptions.RequestException:
            return None

    def get_res(self, url, params=None, allow_redirects=True, stream=False):
        """
        发送 GET 请求，但与上面的 get() 不同，它返回的是原始的 【Response 对象】。
        适合在上层代码需要获取状态码 (r.status_code) 或响应头 (r.headers) 的详细情况时使用。
        
        :param url: 请求地址
        :param params: 查询参数字典
        :param allow_redirects: 是否允许遇到 301/302 状态码时自动重定向（默认 True）
        :param stream: 是否由调用方按块消费响应体
        :return: requests.Response 对象，网络异常时返回 None
        """
        try:
            if self._session:
                return self._session.get(url,
                                         params=params,
                                         verify=self._verify,
                                         headers=self._headers,
                                         proxies=self._proxies,
                                         cookies=self._cookies,
                                         timeout=self._timeout,
                                         allow_redirects=allow_redirects,
                                         stream=stream)
            else:
                return requests.get(url,
                                    params=params,
                                    verify=self._verify,
                                    headers=self._headers,
                                    proxies=self._proxies,
                                    cookies=self._cookies,
                                    timeout=self._timeout,
                                    allow_redirects=allow_redirects,
                                    stream=stream)
        except requests.exceptions.RequestException:
            return None

    def post_res(self, url, params=None, allow_redirects=True, files=None, json=None,
                 stream=False):
        """
        发送 POST 请求，并返回原始的 【Response 对象】。支持上传文件。
        
        :param url: 请求地址
        :param params: 表单数据
        :param allow_redirects: 是否允许重定向
        :param files: 需要上传的文件字典，用于处理文件上传接口
        :param json: JSON 格式数据
        :param stream: 是否由调用方按块消费响应体
        :return: requests.Response 对象，网络异常时返回 None
        """
        try:
            if self._session:
                return self._session.post(url,
                                          data=params,
                                          verify=self._verify,
                                          headers=self._headers,
                                          proxies=self._proxies,
                                          cookies=self._cookies,
                                          timeout=self._timeout,
                                          allow_redirects=allow_redirects,
                                          files=files,  # 支持文件上传
                                          json=json,
                                          stream=stream)
            else:
                return requests.post(url,
                                     data=params,
                                     verify=self._verify,
                                     headers=self._headers,
                                     proxies=self._proxies,
                                     cookies=self._cookies,
                                     timeout=self._timeout,
                                     allow_redirects=allow_redirects,
                                     files=files,
                                     json=json,
                                     stream=stream)
        except requests.exceptions.RequestException:
            return None

    @staticmethod
    def cookie_parse(cookies_str, array=False):
        """
        静态方法：将从浏览器开发者工具复制的 Cookie 字符串解析成 Python 字典或列表。
        【知识点】@staticmethod 装饰器表示这是一个独立工具函数，即使不实例化（不创建对象）也可以直接调用。
        
        举例：
        将 "id=1; name=test" 转换为 {"id": "1", "name": "test"}
        
        :param cookies_str: 原始的 Cookie 字符串
        :param array: 是否将结果返回为特定的字典列表格式，如 [{'name': 'id', 'value': '1'}, ...]
        :return: 解析后的字典或列表
        """
        # 如果传入空字符串，直接返回空字典
        if not cookies_str:
            return {}
            
        cookie_dict = {}
        # 先以分号 ";" 分割每一个 cookie 键值对
        cookies = cookies_str.split(';')
        for cookie in cookies:
            # 再以等号 "=" 分割出“键”和“值”
            cstr = cookie.split('=', 1)
            if len(cstr) > 1:
                # strip() 用于去除字符串首尾多余的空格（因为有时分号后面会跟着一个空格）
                cookie_dict[cstr[0].strip()] = cstr[1].strip()
                
        # 如果调用者要求返回列表格式（有些特定的库需要这种格式的 Cookie）
        if array:
            cookiesList = []
            for cookieName, cookieValue in cookie_dict.items():
                cookies = {'name': cookieName, 'value': cookieValue}
                cookiesList.append(cookies)
            return cookiesList
            
        # 默认返回字典格式，方便 requests 库直接使用
        return cookie_dict
