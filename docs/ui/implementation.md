# Web UI 重构交付记录

本轮已完成完整提示词、11 张 AI 设计参考板、全站 UI 代码重构、实际页面截图和可复用 Skill。界面继续使用 Flask/Jinja、Lit 与既有 Tabler 行为组件；无需迁移后端语言或数据模型。

## 页面与设计覆盖

- [全页提示词](page-prompts.md)：35 个页面画板、8 类动态列表、42 类弹层/菜单、10 类状态；按公共前缀和目标页面增量即可复制生成。
- [AI 参考板](designs/)：覆盖媒体、资源、站点、下载、工具、设置、登录、错误、深色、移动和 API 文档。原图英文提示词及后续修订在 [prompts/](prompts/)。
- [实际运行截图](verification/pages/)：历史桌面完整页面截图，另外保留移动、深色、统计与下载弹窗的截图；[画廊](gallery.html)可快速浏览。
- [页面清单](page-inventory.md)区分真实 URL、共享模板与动态变体，避免把同模板误当成漏页。

生成图属于视觉参考：部分 AI 小字和控件超出了当前功能，其内容不能直接作为接口规格。实现保留真实字段、认证、操作与 AGPL-3.0 许可证；例如只提供实际注册的 Telegram 通知渠道，不加入图中偶发的额外渠道、播放、收藏或虚构下载统计。未为 42 类弹层的每一个状态单独生成位图；它们通过详细提示词、统一组件及代表性弹层参考板覆盖。

## 实现内容

- `design-system.css` 统一字体、颜色、间距、圆角、控件、表格、表单、弹层、明暗主题及响应式断点。
- 深森林色侧栏、统一搜索顶栏、当前页状态、消息入口、移动导航与跳转主内容链接。
- `macro/ui.html` 复用页面标题与表单分区；业务页面迁移共用结构，关联表单标签，删除重复的手机/桌面操作按钮。
- 海报卡常显片名、年份与资源搜索入口；人物卡、详情和列表复用媒体组件。横向浏览支持键盘操作，列表提供加载更多、空态与失败重试。
- 下载任务使用紧凑行；站点、工具、下载器、规则卡及长表单统一结构。统计图使用同一主题，并随容器变化调整尺寸、离页释放实例。
- 登录、403/404/500 使用统一品牌与恢复操作；Swagger 通过 `swagger-ui-css.html` 官方模板扩展点换肤，保留原文档渲染与接口交互。
- 修复中文输入法 Enter 误触发搜索；修复下载弹窗遗留同步请求，先异步加载预设再请求目录；修复 Tabler 默认样式对侧栏和共用页头布局的覆盖。

## 单管理员模式验证（2026-10-17）

已移除账号管理页面、增删用户弹窗、导航权限过滤和受限账号分支。基础设置保留唯一管理员的用户名与密码，登录后的导航展示全部功能。

| 检查 | 结果 |
|---|---|
| Python 全套回归（含认证边界、旧用户表清理与备份） | 410 项通过 |
| `scripts/preview_ui.py --check` | 43 个页面/变体通过，11 个写入入口被拦截 |
| `tests.test_frontend_assets` | 4 项通过 |
| `scripts/verify_ui_navigation.cjs` | 21 个管理员入口、默认页、显式入口、历史恢复与手机导航通过，旧账号管理地址返回 404 |
| `scripts/verify_ui_settings_actions.cjs` | 19 项通过，包含管理员用户名与密码保存请求 |
| `scripts/verify_ui_responsive.cjs` | 32 个页面/视口组合和 5 项交互检查通过 |
| Jinja / JS / diff | 预览模板渲染、修改模块与脚本语法、空白检查通过 |

浏览器验证使用本机只读预览，设置保存等动作由浏览器拦截模拟；未连接或修改真实站点、下载器和生产配置。此次响应式截图与报告仅保存到临时目录，以下历史截图保持原版本记录。

## 历史验证记录

以下记录对应此前 UI 重构，不代表当前单管理员改动已完成相同范围的验证。已移除退役账号管理页的截图和结果，保留原验证时间。

| 检查 | 结果 |
|---|---|
| 既有回归测试 `tests/run.py` | 145 项通过 |
| 隔离预览 `scripts/preview_ui.py --check` | 44 个页面/变体/文档路径通过，11 个写入入口被拦截 |
| [全页浏览器报告](verification/browser-results.json) | 保留的桌面页面 HTTP 200、无 JS 运行错误、无页面横向溢出 |
| [响应式报告](verification/responsive-results.json) | 保留的代表页面 × 390/768/992/1440px，无 JS 错误、无溢出，导航/顶栏尺寸正确 |
| 响应式交互检查 | 深色背景、中文输入法、搜索提交、手机导航、密码显隐共 5 项通过 |
| [统计图专项](verification/statistics-results.json) | 浅深色 token、390px 主图、768px 弹窗、离页释放通过 |
| Jinja / JS / Python | 模板解析、修改模块语法、Python compileall、diff 空白检查通过 |
| Skill | 官方校验脚本通过；复用项目 ruamel.yaml 安全解析器提供 YAML 接口 |

这些浏览器结果来自真实模板和静态资源，但数据由内存示例提供。未连接真实站点、下载器、TMDB、Telegram，也没有执行下载、删除、签到、发消息或保存生产配置。真实外部集成仍需要使用者在部署环境联调。

## 本地复核

```bash
.venv/bin/python scripts/preview_ui.py --port 5108
# 在另一个终端运行；需要本机可用的 Playwright / Chrome。
NODE_PATH=/path/to/node_modules node scripts/verify_ui.cjs
NODE_PATH=/path/to/node_modules node scripts/verify_ui_responsive.cjs
NODE_PATH=/path/to/node_modules node scripts/verify_ui_navigation.cjs
```

打开 `http://127.0.0.1:5108/preview` 可逐页查看。预览脚本固定监听本机，只用公开 UI 描述和内存样例，不加载运行配置、数据库或调度器；所有写操作均被拦截。

## 后续统一性

[Skill 源文件](skill/nas-tools-ui/SKILL.md)已安装到 `~/.codex/skills/nas-tools-ui/SKILL.md`，可通过 `$nas-tools-ui` 调用，也可自动匹配本项目的 UI 工作。后续新增页面复用 `--nt-*` tokens、Jinja 宏和 Lit 组件，并更新页面清单与提示词。

本次 UI 重构随 `0.7.0` 发布，代码、设计参考、提示词、验证脚本与截图一并纳入版本控制。本轮不执行部署。
