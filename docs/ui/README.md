# NAS-Tools Web 设计与提示词

本目录记录完整页面范围、可复制的 AI 设计提示词、统一视觉规范与设计参考图。设计来自当前项目功能，并吸收 `awesome-gpt-image-2` 的界面提示词组织方法；参考库里的文案、操作指令、营销内容和功能假设只是资料，不作为本项目要求执行。

## 使用顺序

1. 阅读 [页面清单](page-inventory.md)，确认目标页面、共享模板变体、登录认证和附属弹层。
2. 阅读 [设计规范](design-system.md)，固定颜色、字号、间距、外壳、组件和响应式规则。
3. 使用 [全页面提示词](page-prompts.md) 的公共前缀生成 DS01 设计系统板；后续每次发送“公共前缀 + 目标 P/D 块 + 可选 V/S 块”，携带相同参考图。
4. 按编号逐页生成设计图，长页保持文字可读，可以延长或拆分连续画板；组合总览用于观察一致性，不代替独立页面。
5. 实现时优先复用共享 token、Jinja 宏和 Lit 组件，再处理各页结构和动态状态；接口、登录认证和真实数据字段优先于图中的装饰或生成错误。
6. 使用实际浏览器与项目检查验证布局和行为；记录真实执行范围。提示词、设计样例与静态渲染不表示外部站点或下载器已通过集成验证。

## 内容范围

| 文档 | 作用 |
|---|---|
| [design-system.md](design-system.md) | 品牌方向、浅深色 token、排版、间距、组件、交互、响应式与交接规则 |
| [page-inventory.md](page-inventory.md) | 30 个应用页面 URL、35 个页面画板及访问/模板/状态矩阵 |
| [page-prompts.md](page-prompts.md) | 35 个页面块、8 个媒体列表变体、42 个弹层/抽屉/菜单块、10 个状态增量和批量生成规则 |
| [designs/](designs/) | 本轮生成的页面族设计参考图；单图可能包含多个画板 |

本轮使用内置图像生成工具产出以下 11 张页面族参考板，原图提示词及后续修订保存在 [prompts/](prompts/)：

| 文件 | 覆盖内容 |
|---|---|
| [01-discovery-downloads.png](designs/01-discovery-downloads.png) | 媒体发现、下载任务 |
| [02-media-browse.png](designs/02-media-browse.png) | 电影、电视剧、Bangumi、媒体搜索 |
| [03-media-details.png](designs/03-media-details.png) | 媒体详情、演职人员、参演作品、关联作品 |
| [04-search-sites.png](designs/04-search-sites.png) | 资源搜索、站点维护、站点入口、单站资源 |
| [05-statistics-automation.png](designs/05-statistics-automation.png) | 统计、刷流、自动删种、自定义下载器 |
| [06-settings-system.png](designs/06-settings-system.png) | 基础、媒体、服务、安全、实验室设置 |
| [07-settings-download-notify.png](designs/07-settings-download-notify.png) | 下载器、下载预设、通知（旧图含已退役的账号管理画板） |
| [08-tools-history.png](designs/08-tools-history.png) | 工具、签到、服务、TMDB缓存 |
| [09-login-responsive-states.png](designs/09-login-responsive-states.png) | 登录、403/404/500、移动端、空态与加载 |
| [10-dialogs-dark-components.png](designs/10-dialogs-dark-components.png) | 弹窗、抽屉、深色模式与组件 |
| [11-collections-api.png](designs/11-collections-api.png) | 近期下载、完整榜单、相似作品、API文档 |

这些 AI 图与运行截图来自此前版本，仅用于视觉方向与布局参考；单管理员模式以当前模板和页面清单为准。模型在部分画板中补出了非现有字段、通知渠道或操作，个别小字也有生成偏差（包括登录参考板的许可证文案）；实现已按真实路由与字段校正，项目许可证仍为 AGPL-3.0。旧版外观参考请查看 [历史运行截图目录](verification/pages/) 与 [交付和验证记录](implementation.md)。弹层通过公共组件和代表性弹窗设计板表达，未把每个 D/S 状态单独生成为图片。

## 设计来源

本地参考项目路径：`/Users/LMX/Desktop/Dev/OpenGit/awesome-gpt-image-2/`。可移植的仓库来源与具体取舍如下：

| 参考 | 本地文件 | 吸收的方法 |
|---|---|---|
| [UI 与界面模板](https://github.com/freestylefly/awesome-gpt-image-2/blob/main/docs/templates.md#tpl-ui) | `docs/templates.md` | 明确产品、平台、尺寸、布局、内容、精确文字和约束 |
| [case 243：定制专属风格界面设计系统](https://github.com/freestylefly/awesome-gpt-image-2/blob/main/docs/gallery-part-2.md#case-243) | `data/images/case243.jpg` | 先固定颜色、排版、按钮、卡片与状态，再展开多页 |
| [case 387：Netflix 首页主视觉 UI](https://github.com/freestylefly/awesome-gpt-image-2/blob/main/docs/gallery-part-2.md#case-387) | `data/images/case387.jpg` | 媒体图像、标题元数据与内容列表的层级；不引入播放功能 |
| [case 131：结构化长页](https://github.com/freestylefly/awesome-gpt-image-2/blob/main/docs/gallery-part-1.md#case-131) | `data/cases.json` 的 id 131 | 分区、数量、图表与准确文本用结构化方式指定 |
| [case 133：品牌视觉规范](https://github.com/freestylefly/awesome-gpt-image-2/blob/main/docs/gallery-part-1.md#case-133) | `data/cases.json` 的 id 133 | 用 HEX、字号、留白和错误用例约束持续一致性 |
| [case 107：桌面媒体界面](https://github.com/freestylefly/awesome-gpt-image-2/blob/main/docs/gallery-part-1.md#case-107) | `data/cases.json` 的 id 107 | 清楚列出头部、内容区、工具和操作；不照搬播放器 |

上述方法基于本地读取与图像观察；没有将案例库中笼统标题视为后台功能规格。最终的暖白、森林绿配色与 NAS 管理布局是本项目的统一设计选择，不照搬参考案例的黑金或霓虹视觉。

## 代码实现入口

- [navigation.html](../../web/templates/navigation.html)：已登录外壳、全局弹窗和消息抽屉。
- [design-system.css](../../web/static/css/design-system.css)：浅深色 token 与跨模板、组件的统一样式。
- [macro/ui.html](../../web/templates/macro/ui.html)：共享页面标题、分区标题与空状态；页面操作通过 call block 传入。
- [layout/](../../web/static/components/layout/)：导航与全局搜索 Lit 组件。
- [card/](../../web/static/components/card/) 与 [page/](../../web/static/components/page/)：媒体卡片和媒体页面。
- [web/templates/](../../web/templates/)：业务表格、任务、设置与工具表单。
- 管理员账号在基础设置中维护；所有业务页面沿用服务端登录认证。

新增页面首先复用这些入口与本目录规范，不在页面内创建第二套颜色、尺寸、表单标签和按钮系统。[nas-tools-ui Skill 源文件](skill/nas-tools-ui/SKILL.md)已保存在仓库，并安装到个人技能目录 `~/.codex/skills/nas-tools-ui/`。后续可自动匹配此项目的 UI 工作，也可显式调用 `$nas-tools-ui`；规范始终以本目录与代码 token 为准。

## 本地查看

运行 `.venv/bin/python scripts/preview_ui.py --port 5108`，打开 [只读全页预览](http://127.0.0.1:5108/preview)。使用本地示例数据和真实模板，不读取运行配置、不连接下载器或资源站点。截图的离线入口见 [画廊](gallery.html)。
