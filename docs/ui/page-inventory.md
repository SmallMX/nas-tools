# Web 页面与状态清单

清单以 [主路由](../../web/main.py)、[工具路由](../../web/routes/tool_pages.py)、[权限声明](../../web/permissions.py)、Jinja 模板与 Lit 组件为依据。共有 **31 个应用页面 URL**：根路径 `/` 分别承载登录与已登录外壳，因此对应 **32 个应用视图**；再加 **403 / 404 / 500 三个错误视图**及 **一个独立 Swagger 文档视图**，提示词共编号 P01–P36。

页面权限与操作权限分别检查。下面的权限列是阅读设计时的摘要，授权实现以 `web/permissions.py` 为准；界面重排不能改变权限。API JSON 响应、上传、目录数据、健康检查和 Webhook 不作为普通页面重复计数，目录选择等可视交互计入弹层清单。

## 路由、模板与提示词矩阵

| 编号 | 页面 | 路由 / 场景 | 模板或入口 | 权限 |
|---|---|---|---|---|
| P01 | 登录 | `/（未登录）` | [login.html](../../web/templates/login.html) | 公开登录入口 |
| P02 | 应用外壳与导航 | `/（已登录）` | [navigation.html](../../web/templates/navigation.html) | 登录后按权限显示 |
| P03 | 榜单推荐 | `/ranking` | [discovery/ranking.html](../../web/templates/discovery/ranking.html) | 探索 |
| P04 | TMDB 电影 | `/tmdb_movie` | [discovery/recommend.html](../../web/templates/discovery/recommend.html) | 探索 |
| P05 | TMDB 电视剧 | `/tmdb_tv` | [discovery/recommend.html](../../web/templates/discovery/recommend.html) | 探索 |
| P06 | Bangumi 每日放送 | `/bangumi` | [discovery/ranking.html](../../web/templates/discovery/ranking.html) | 探索 |
| P07 | 通用媒体列表 | `/recommend` | [discovery/recommend.html](../../web/templates/discovery/recommend.html) | 探索；数据动作按来源检查 |
| P08 | 媒体详情 | `/media_detail?id=&type=` | [discovery/mediainfo.html](../../web/templates/discovery/mediainfo.html) | 探索；搜索/下载另按权限 |
| P09 | 演职人员 | `/discovery_person?tmdbid=&type=&title=&subtitle=` | [discovery/person.html](../../web/templates/discovery/person.html) | 探索 |
| P10 | 资源搜索结果 | `/search` | [search.html](../../web/templates/search.html) | 资源搜索；下载操作需下载管理 |
| P11 | 站点维护 | `/site` | [site/site.html](../../web/templates/site/site.html) | 站点管理；凭据同步需系统设置 |
| P12 | 站点资源入口 | `/sitelist` | [site/sitelist.html](../../web/templates/site/sitelist.html) | 站点管理 |
| P13 | 站点资源列表 | `/resources?site=&title=&page=&keyword=` | [site/resources.html](../../web/templates/site/resources.html) | 站点管理；下载操作需下载管理 |
| P14 | 数据统计 | `/statistics` | [site/statistics.html](../../web/templates/site/statistics.html) | 站点管理 |
| P15 | 刷流任务 | `/brushtask` | [site/brushtask.html](../../web/templates/site/brushtask.html) | 服务 |
| P16 | 自定义下载器 | `/userdownloader` | [download/userdownloader.html](../../web/templates/download/userdownloader.html) | 系统设置 |
| P17 | 正在下载 | `/downloading` | [download/downloading.html](../../web/templates/download/downloading.html) | 下载管理 |
| P18 | 近期下载 | `/downloaded` | [discovery/recommend.html](../../web/templates/discovery/recommend.html) | 下载管理 |
| P19 | 自动删种任务 | `/torrent_remove` | [download/torrent_remove.html](../../web/templates/download/torrent_remove.html) | 下载管理 |
| P20 | 工具中心 | `/tools` | [tools/index.html](../../web/templates/tools/index.html) | 登录；卡片按工具权限 |
| P21 | 站点自动签到 | `/tools/site-signin` | [tools/site_signin.html](../../web/templates/tools/site_signin.html) | 站点管理 |
| P22 | 服务 | `/service` | [service.html](../../web/templates/service.html) | 服务或系统设置；各卡片分别授权 |
| P23 | TMDB 缓存 | `/tmdbcache?pagenum=&s=&page=` | [rename/tmdbcache.html](../../web/templates/rename/tmdbcache.html) | 系统设置 |
| P24 | 基础设置 | `/basic` | [setting/basic.html](../../web/templates/setting/basic.html) | 系统设置 |
| P25 | 媒体设置 | `/media_setting` | [setting/basic.html](../../web/templates/setting/basic.html) | 系统设置 |
| P26 | 服务设置 | `/service_setting` | [setting/basic.html](../../web/templates/setting/basic.html) | 系统设置 |
| P27 | 安全设置 | `/security_setting` | [setting/basic.html](../../web/templates/setting/basic.html) | 系统设置 |
| P28 | 实验室 | `/laboratory_setting` | [setting/basic.html](../../web/templates/setting/basic.html) | 系统设置 |
| P29 | 下载器设置 | `/downloader` | [setting/downloader.html](../../web/templates/setting/downloader.html) | 系统设置 |
| P30 | 下载设置预设 | `/download_setting` | [setting/download_setting.html](../../web/templates/setting/download_setting.html) | 系统设置 |
| P31 | 消息通知 | `/notification` | [setting/notification.html](../../web/templates/setting/notification.html) | 系统设置；自定义消息动作按现有权限 |
| P32 | 用户管理 | `/users` | [setting/users.html](../../web/templates/setting/users.html) | 系统设置 |
| P33 | 403 无权限 | `403 错误处理器` | [403.html](../../web/templates/403.html) | 无权访问时 |
| P34 | 404 页面不存在 | `404 错误处理器` | [404.html](../../web/templates/404.html) | 错误处理 |
| P35 | 500 服务异常 | `500 错误处理器` | [500.html](../../web/templates/500.html) | 错误处理 |
| P36 | Swagger API 文档 | `/api/v1/` | [web/apiv1.py](../../web/apiv1.py) | 文档及 API 执行遵循现有鉴权 |

## 动态页面不可遗漏的变体

`discovery/recommend.html` 承载多个用户任务，不能只因共享模板就只设计一次。对应完整提示词在 [V01–V08](page-prompts.md#通用媒体列表的独立变体)。

| 编号 | 来源 | 参数语义 | 需要保留的差异 |
|---|---|---|---|
| V01 | 媒体关键词搜索 | `type=SEARCH` | 元数据匹配结果，不是种子表 |
| V02 | 榜单查看全部 | `榜单传入的 type/subtype/title` | 标题和顺序来自被展开榜单 |
| V03 | Bangumi 单日 | `subtype=bangumi 与对应 week` | 星期与番剧上下文 |
| V04 | 人物作品 | `subtype=person 与 personid` | 人物姓名和参演作品 |
| V05 | 类似媒体 | `subtype=sim 与 tmdbid` | 来源片名与类似关系 |
| V06 | 推荐媒体 | `subtype=more 与 tmdbid` | 来源片名与推荐关系 |
| V07 | 筛选结果 | `type=DISCOVER 与 filter/params` | 动态筛选项、当前选择和分页 |
| V08 | 近期下载来源 | `type=DOWNLOADED；独立入口 /downloaded` | 日期、站点和下载管理权限 |

`discovery/ranking.html` 还分别承载九个现有榜单分区与 Bangumi 周一至周日分区；`setting/basic.html` 通过 `SettingSection` 独立承载 system、media、service、security、laboratory 五个真实页面。每条路由保留独立标题和字段，不能渲染成一个无限长的混合设置页。

## 弹层、抽屉与附属画板

源码有 38 种 modal 模板定义，动态 qBittorrent / Transmission 展开后为 39 个实例；搜索过滤按媒体重复。下表按用户界面实例列出 D01–D39，再补消息中心、移动导航、目录选择和共享菜单 D40–D43。列表数量包含实现定义、动态实例和设计规格三个不同层次，不能直接用一个数量相互替代。

| 编号 | 场景 | 来源 |
|---|---|---|
| D01 | 等待反馈 | `navigation.html · modal-wait` |
| D02 | 操作进度 | `navigation.html · modal-process` |
| D03 | 危险操作确认 | `navigation.html · system-confirm-modal` |
| D04 | 成功后继续操作 | `navigation.html · system-success-action-modal` |
| D05 | 二选一询问 | `navigation.html · system-ask-modal` |
| D06 | 成功反馈 | `navigation.html · system-success-modal` |
| D07 | 失败反馈 | `navigation.html · system-fail-modal` |
| D08 | 媒体速览 | `navigation.html · system-media-modal` |
| D09 | 实时日志 | `navigation.html · modal-logging` |
| D10 | 添加下载 | `navigation.html · modal-search-download` |
| D11 | 高级搜索 | `navigation.html · modal-search-advanced` |
| D12 | 搜索结果筛选 | `search.html · search-filter-modal-{media}` |
| D13 | 站点新增与编辑 | `site/site.html · modal-site` |
| D14 | 站点连通性测试 | `site/site.html · modal-sitetest` |
| D15 | 更新站点凭据 | `site/site.html · modal-update-site-cookie` |
| D16 | CookieCloud 数据同步 | `site/site.html · modal-cookiecloud` |
| D17 | 输入验证码 | `site/site.html · modal-captcha-code` |
| D18 | 站点活动信息 | `site/statistics.html · site-activity` |
| D19 | 站点做种明细 | `site/statistics.html · site-seeding-info` |
| D20 | 统计分享设置与导出图 | `site/statistics.html · modal-statistics-pic-setting` |
| D21 | 刷流任务新增与编辑 | `site/brushtask.html · modal-brushtask` |
| D22 | 刷流种子明细 | `site/brushtask.html · modal-brushtask-torrents` |
| D23 | 自定义下载器新增与编辑 | `download/userdownloader.html · modal-add-downloader` |
| D24 | 自动删种任务新增与编辑 | `download/torrent_remove.html · modal-torrent-remove-task` |
| D25 | 自动删种预处理列表 | `download/torrent_remove.html · modal-remove-torrents` |
| D26 | 名称识别测试 | `service.html · modal-nametest` |
| D27 | 网络连通性测试 | `service.html · modal-nettest` |
| D28 | 配置备份 | `service.html · modal-backup` |
| D29 | 缓存 JSON 详情 | `rename/tmdbcache.html · tmdb_cache_detail` |
| D30 | 修改 TMDB 缓存 | `rename/tmdbcache.html · modal-tmdbcache-modify` |
| D31 | 自定义 CSS / JavaScript | `setting/basic.html · modal-user-script` |
| D32 | 自定义制作组 / 字幕组 | `setting/basic.html · modal-release-groups` |
| D33 | qBittorrent 连接设置 | `setting/downloader.html · modal-{{ Type }} 的 qBittorrent 实例` |
| D34 | Transmission 连接设置 | `setting/downloader.html · modal-{{ Type }} 的 Transmission 实例` |
| D35 | 下载目录配置 | `setting/downloader.html · modal-downloaddir` |
| D36 | 下载设置预设编辑 | `setting/download_setting.html · modal-download-setting` |
| D37 | 通知客户端新增与编辑 | `setting/notification.html · modal-message-client` |
| D38 | 发送自定义消息 | `setting/notification.html · modal-send-custom-message` |
| D39 | 新增用户 | `setting/users.html · modal-user` |
| D40 | 消息中心抽屉 | `navigation.html · offcanvasEnd` |
| D41 | 移动导航抽屉 | `layout/navbar/index.js · litLayoutNavbar` |
| D42 | 目录树选择 | `运行时 /dirlist 目录树` |
| D43 | 菜单与帮助浮层 | `全局搜索、用户菜单、任务菜单、筛选菜单、tooltip` |

## 状态覆盖矩阵

“需要”表示设计与验收范围，不表示此轮已经在真实浏览器逐项验证。

| 页面族 | 默认内容 | 加载 | 初次空 / 无结果 | 失败 | 权限差异 | 手机 / 平板 | 深色 |
|---|---|---|---|---|---|---|---|
| 登录 | 表单 | 提交中 | 空字段校验 | 登录错误 | 登录后跳转 | 需要 | 需要 |
| 外壳 | 按权限的导航与搜索 | 外壳准备 | 无可用入口 | 初始化失败 | 菜单/操作隐藏 | 抽屉/搜索 | 需要 |
| 媒体发现与详情 | 海报/人员/元数据 | 卡片骨架 | 无条目/缺图/无评分 | 来源失败 | 详情/搜索动作 | 网格减列 | 需要 |
| 资源搜索与站点资源 | 分组/表格 | 请求中 | 无结果/筛选无匹配 | 站点搜索失败 | 下载入口 | 筛选弹层/表格滚动 | 需要 |
| 下载任务 | 速度/进度/菜单 | 数据刷新 | 无任务 | 操作失败 | 管理入口 | 紧凑任务行 | 需要 |
| 站点与规则 | 卡片/配置摘要 | 读取/执行中 | 尚未配置/未命中 | 连接/执行失败 | 同步/服务权限 | 卡片单列 | 需要 |
| 统计 | 指标/图表/表格 | 局部刷新 | 暂无数据 | 部分站点失败 | 分享/管理入口 | 图表堆叠 | 需要 |
| 工具与签到 | 设置/状态/历史 | 执行中 | 无站点/无历史 | 重试与保存失败 | 工具可见范围 | 表单单列 | 需要 |
| 设置与用户 | 字段/开关/预设 | 保存/测试中 | 尚未配置 | 字段/请求失败 | 密钥与管理范围 | 单列/长弹层 | 需要 |
| 弹窗/抽屉 | 正文/操作 | 局部加载 | 空正文/无匹配 | 原因反馈 | 内容与触发入口 | 可滚动/焦点 | 需要 |
| 403/404/500 | 状态说明/返回首页 | 不适用 | 不适用 | 页面本身即错误 | 不泄露内容 | 需要 | 需要 |
| Swagger | 分组/接口/schema | 文档加载 | 无接口内容时的实际状态 | schema/请求错误 | 鉴权与执行 | 长路径/代码滚动 | 独立资源验证 |

## 功能边界

- 当前主下载器为 qBittorrent 和 Transmission；当前通知客户端类型为 Telegram。
- 未发现可作为本轮页面设计依据的订阅、媒体整理、Emby/Jellyfin、企业微信或付费页面，不能从上游 NAS-Tools 印象补入。
- `/tools` 目前按权限展示“站点自动签到”；不能把工具卡自动扩成插件市场。
- `/downloading` 的模板直接使用标题、速度文本、进度和控制动作。设计图中的独立总大小、预计完成时间、状态 Tabs 等如果没有字段支持，应移除。
- `/service` 的网络测试和备份只对系统设置权限显示；名称识别测试按服务权限显示。刷流页面权限为服务，自定义下载器权限为系统设置。
- `/api/v1/` 是 Flask-RESTX 自动生成的 Swagger 页面；需独立处理其主题资源和协议交互，不可假定主应用样式自然生效。

## 新增页面时更新

先增加路由与权限声明，再补本表和 [页面提示词](page-prompts.md) 的独立块。共享模板新增一种用户任务时，补一个变体块；新增弹窗时补 D 类规格；新增后台接口但没有独立 UI 时，不虚增一个页面编号。确认旧链接、动态字段、表单 ID 与脚本绑定仍对应真实实现。
