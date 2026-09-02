"""站点自动签到工具常量。"""

DEFAULT_RETRY_KEYWORD = r"错误|失败|失效|无法|超时|Cloudflare"

SITE_CHECKIN_XPATH = (
    '//a[@id="signed"]',
    '//a[contains(@href, "attendance")]',
    '//a[contains(text(), "签到")]',
    '//a/b[contains(text(), "签 到")]',
    '//span[@id="sign_in"]/a',
    '//a[contains(@href, "addbonus")]',
    '//input[@class="dt_button"][contains(@value, "打卡")]',
    '//a[contains(@href, "sign_in")]',
    '//a[contains(@onclick, "do_signin")]',
    '//a[@id="do-attendance"]',
)
