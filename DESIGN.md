---
name: NAS-Tools
description: 有序的媒体工作台：清晰、紧凑、克制，便于日常管理。
colors:
  nt-primary: '#187761'
  nt-primary-soft: '#e7f2eb'
  nt-canvas: '#f5f6f2'
  nt-surface: '#fff'
  nt-surface-secondary: '#eef2ec'
  nt-text: '#20332d'
  nt-muted: '#607166'
  nt-border: '#dee5dd'
  nt-warning: '#b77920'
  nt-danger: '#bd4c42'
  nt-sidebar: '#142923'
  nt-sidebar-text: '#d3e0d7'
  nt-primary-dark: '#65c8a8'
  nt-primary-soft-dark: '#244638'
  nt-canvas-dark: '#101b17'
  nt-surface-dark: '#192923'
  nt-surface-secondary-dark: '#22372e'
  nt-text-dark: '#e7eee9'
  nt-muted-dark: '#a5b6ac'
  nt-border-dark: '#33493d'
  nt-warning-dark: '#e5b362'
  nt-danger-dark: '#f08b80'
  on-primary: '#fff'
  on-primary-dark: '#10291f'
  nav-hover: '#254438'
  nav-active: '#e7f2eb'
  nav-active-text: '#185b47'
  nav-active-hover: '#d9eadd'
typography:
  headline:
    fontFamily: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Noto Sans SC", "Microsoft YaHei", sans-serif
    fontSize: 28px
    fontWeight: 650
    lineHeight: 1.3
    letterSpacing: -0.6px
  headline-mobile:
    fontFamily: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Noto Sans SC", "Microsoft YaHei", sans-serif
    fontSize: 24px
    fontWeight: 650
    lineHeight: 1.3
    letterSpacing: -0.6px
  title:
    fontFamily: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Noto Sans SC", "Microsoft YaHei", sans-serif
    fontSize: 18px
    fontWeight: 600
    lineHeight: 1.4
    letterSpacing: -0.2px
  body:
    fontFamily: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Noto Sans SC", "Microsoft YaHei", sans-serif
    fontSize: 14px
    fontWeight: 400
    lineHeight: 1.6
  label:
    fontFamily: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Noto Sans SC", "Microsoft YaHei", sans-serif
    fontSize: 13px
    fontWeight: 550
    lineHeight: 1.6
  button:
    fontFamily: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Noto Sans SC", "Microsoft YaHei", sans-serif
    fontSize: 13px
    fontWeight: 550
    lineHeight: 1.4285714286
  input:
    fontFamily: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Noto Sans SC", "Microsoft YaHei", sans-serif
    fontSize: 14px
    fontWeight: 400
    lineHeight: 20px
  input-mobile:
    fontFamily: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Noto Sans SC", "Microsoft YaHei", sans-serif
    fontSize: 16px
    fontWeight: 400
    lineHeight: 1.4285714286
  caption:
    fontFamily: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Noto Sans SC", "Microsoft YaHei", sans-serif
    fontSize: 12px
    fontWeight: 400
    lineHeight: 1.6
  media-title:
    fontFamily: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Noto Sans SC", "Microsoft YaHei", sans-serif
    fontSize: 14px
    fontWeight: 600
    lineHeight: 1.5
  media-meta:
    fontFamily: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Noto Sans SC", "Microsoft YaHei", sans-serif
    fontSize: 12px
    fontWeight: 400
    lineHeight: 1.5
rounded:
  nt-radius: 12px
  nt-control-radius: 8px
  dropdown: 10px
  modal: 16px
  nav-item: 7px
  badge: 5px
  menu-item: 6px
spacing:
  nt-space-1: 4px
  nt-space-2: 8px
  nt-space-3: 12px
  nt-space-4: 16px
  nt-space-6: 24px
  nt-space-8: 32px
components:
  button-primary:
    backgroundColor: '{colors.nt-primary}'
    textColor: '{colors.on-primary}'
    typography: '{typography.button}'
    rounded: '{rounded.nt-control-radius}'
    padding: 8px 14px
  button-primary-dark:
    backgroundColor: '{colors.nt-primary-dark}'
    textColor: '{colors.on-primary-dark}'
    typography: '{typography.button}'
    rounded: '{rounded.nt-control-radius}'
    padding: 8px 14px
  button-outline-primary:
    textColor: '{colors.nt-primary}'
    typography: '{typography.button}'
    rounded: '{rounded.nt-control-radius}'
    padding: 8px 14px
  button-danger:
    backgroundColor: '{colors.nt-danger}'
    textColor: '{colors.on-primary}'
    typography: '{typography.button}'
    rounded: '{rounded.nt-control-radius}'
    padding: 8px 14px
  text-field:
    backgroundColor: '{colors.nt-surface}'
    textColor: '{colors.nt-text}'
    typography: '{typography.input}'
    rounded: '{rounded.nt-control-radius}'
    padding: 8px 12px
  sidebar-nav:
    backgroundColor: '{colors.nt-sidebar}'
    textColor: '{colors.nt-sidebar-text}'
    width: 232px
  filter-chip:
    textColor: '{colors.nt-text}'
    rounded: '{rounded.nt-control-radius}'
    padding: 8px 12px
  surface-card:
    backgroundColor: '{colors.nt-surface}'
    textColor: '{colors.nt-text}'
    rounded: '{rounded.nt-radius}'
    padding: 24px
  media-card:
    textColor: '{colors.nt-text}'
    typography: '{typography.media-title}'
    rounded: '{rounded.nt-radius}'
  empty-state:
    backgroundColor: '{colors.nt-surface}'
    textColor: '{colors.nt-text}'
    rounded: '{rounded.nt-radius}'
    padding: 48px 24px
---

# Design System: NAS-Tools

## Overview

**Creative North Star: "有序的媒体工作台"**

NAS-Tools 的现有界面强调清晰、紧凑、克制，支持媒体浏览与日常管理。暖白画布、森林绿侧栏和薄荷绿强调形成稳定的识别；媒体图像承担内容表达，操作区域保持直接、可扫描。

普通内容主要依靠背景色、细边框和间距分层，阴影集中用于菜单、目录选择器和弹窗。按钮、卡片与输入框保持紧凑、清晰的状态反馈。这些描述已由使用者确认，记录当前方向，不构成重新设计授权。

**Key Characteristics:**

- 暖白与森林绿建立稳定外壳，浅深主题使用相同语义角色。
- 媒体内容突出海报、片名与元数据，管理内容采用分区表单、卡片和任务行。
- 普通卡片保持平面，浮层用有限的阴影说明层级。
- 复用相同组件、术语与状态，兼顾桌面浏览和手机操作。

本文件按 [DESIGN.md 格式](https://github.com/google-labs-code/design.md/blob/main/docs/spec.md)记录当前代码提取的 token 与应用方式；颜色、字号、圆角及间距的机器值以顶部 YAML 为准。CSS token 在文档中去掉 `--` 前缀，深色覆盖使用 `-dark` 后缀；这只是文档映射，不改动 CSS 名称。

实现依据为 [共享样式](web/static/css/design-system.css)、[媒体组件样式](web/static/components/card/media-styles.js)、[导航](web/static/components/layout/navbar/index.js)、[Jinja UI 宏](web/templates/macro/ui.html) 和 Tabler 基础样式。更完整的交互要求继续维护在 [既有 Web 规范](docs/ui/design-system.md)，产品事实见 [PRODUCT.md](PRODUCT.md)。隔离预览用于布局与交互检查，不能替代真实站点／下载器联调或全站无障碍验收；具体执行范围随交付说明记录。

## Colors

色彩以偏绿的中性色为基础，交互强调沿用绿色体系。以下名称对应顶部 token，不另定义第二份颜色值。

### Primary

- **森林绿主色**（`nt-primary`）：浅色主题的主操作、链接、选中状态与焦点；深色对应薄荷绿 `nt-primary-dark`。
- **薄荷浅强调**（`nt-primary-soft`）：轻提示、筛选选中及局部 hover 背景；深色使用 `nt-primary-soft-dark`。
- **主按钮文字**（`on-primary` / `on-primary-dark`）：浅色主按钮使用白字，深色主按钮使用深绿文字。

### Neutral

- **暖白画布**（`nt-canvas`）：页面底色；深色对应 `nt-canvas-dark`。
- **内容表面与次级表面**（`nt-surface`、`nt-surface-secondary`）：卡片、输入框及表头、禁用区；深色采用对应覆盖值。
- **正文、辅助文字与边框**（`nt-text`、`nt-muted`、`nt-border`）：分别承载内容层级和分隔，不用降低全部内容的对比度来制造柔和感。
- **森林绿侧栏**（`nt-sidebar`、`nt-sidebar-text`）：两主题共用固定背景和文字；导航 hover 与选中使用独立 `nav-*` 值，不随内容区主题机械反转。

### Semantic

- **警告与错误**（`nt-warning`、`nt-danger`）：附带状态文字或图标，不能仅用颜色区分结果。
- 危险按钮当前使用固定的浅色错误底色与白字，未跟随深色 `nt-danger-dark`；这是实现现状，不表示所有危险状态都采用相同配色。
- 站点能力徽标、评分等还使用局部业务配色，不将这些局部颜色提升为第二套全局品牌色。
- 资源搜索中的站点、体积、编码和发布组采用中性元数据样式，促销条件使用主色浅强调，避免普通属性与关键状态争夺注意力。

**The 语义随主题 Rule.** 内容区通过同名语义变量切换主题；侧栏保留其固定状态色，不把浅色颜色逐个反转。

`.impeccable/design.json` 的色阶仅为面板展示而从现有颜色推导，不是新增的生产 CSS token，也不授权替换现有颜色。

## Typography

全站共用顶部 token 中的 Inter 与系统字体回退栈，中文由 PingFang SC、Noto Sans SC、Microsoft YaHei 等回退承接。当前没有独立的展示字体，也没有贯穿所有页面的数学字号比例；不要新增一套字体来填补格式中的可选角色。

### Hierarchy

| 角色 | 用途与继承关系 |
|---|---|
| `headline` / `headline-mobile` | 通用页面标题，手机断点缩小；保留标题的紧凑字距 |
| `title` | 分区和普通卡片标题 |
| `body` | 正文与通用内容，行高使用实际比例 |
| `label` / `button` / `input` / `input-mobile` | 表单标签、按钮与输入文字；按钮继承 Tabler 的行高，手机输入文字放大至对应角色 |
| `caption` | 帮助文字、次级说明 |
| `media-title` / `media-meta` | 常显片名与年份等元数据 |

表格和任务进度使用等宽数字。路径和长名称保留可访问的完整内容入口。媒体详情、登录页和错误页有各自的标题例外，不将这些局部字号推广成所有页面的标题规则。

部分旧模板仍存在小型眉题和全大写辅助标签；不将这些遗留装饰登记为新页面的复用排版角色。

## Layout

桌面采用固定左侧导航与顶部搜索栏，主体使用流式容器，上限为 1680px。侧栏宽度为 232px；顶部栏在桌面为 72px，抽屉布局下为 64px。共享间距沿用顶部 `nt-space-*`，同时如实保留组件已经采用的局部尺寸。

| 视口 | 外壳与主内容 |
|---|---|
| ≥992px | 固定侧栏；主内容左右内边距 32px |
| 768–991.98px | 侧栏转抽屉；主内容左右内边距 24px |
| ≤767.98px | 主内容左右内边距 16px；页头操作区可换行，常规卡片内边距缩至 20px |

通用媒体网格以最小 160px 列宽、24px 间距自适应；探索页使用最小 144px 列宽、16px 间距。手机上二者均为两列，但通用媒体网格行间距为 20px，探索页为 16px，列间距均为 12px。不要用一条通用网格规则覆盖所有媒体页面族。

表单沿用现有列与分区，长字段跨列；手机上允许标签、操作行及内容自然换行。来源与筛选行在窄屏内横向滚动，长表格在自己的容器内滚动。

**已记录的文档差异：**旧规范将 992–1199px 的主内容边距写为 24px，当前 CSS 实际仍为 32px；本次记录实现，不修改旧规范或布局。

## Elevation & Depth

普通卡片使用细边框和表面色，默认无阴影。下拉菜单、目录选择器与模态弹窗通过不同强度的阴影表达浮层关系；详细阴影值在 sidecar 的 `extensions.shadows` 中对应各自来源。顶部搜索栏局部存在背景模糊，但同时使用实色表面，不将其定义为全站玻璃材质。

**The 平面内容与浮层 Rule.** 不给普通内容卡片追加浮起效果；需要覆盖原内容的菜单和弹窗才使用各自已有的深度处理。

## Shapes

卡片与海报采用柔和矩形，输入框和按钮使用更小的圆角。顶部 `rounded` 分别记录表面、控件、菜单、弹窗、导航条目和徽标的实际尺寸；菜单项与完整菜单不共用同一个圆角。

海报保持 2:3，人物头像保持圆形裁切，图片加载前保留面积。普通容器用细边框，空状态使用虚线边框；不要把所有矩形都统一为胶囊。

**已记录的文档差异：**旧规范把弹出菜单概括为控件圆角，当前菜单、弹窗与徽标各有独立尺寸。顶部 token 保留当前差异。

## Components

### Buttons

按钮紧凑、清晰，主操作使用主色，次要操作使用描边或中性表面，危险操作保留独立语义。主按钮 hover 通过亮度变化反馈；描边主色按钮 hover 使用浅强调背景。过渡主要是背景色和边框色的 150ms ease，不以位移制造普通操作反馈。

通用按钮桌面最小高度为 38px，小按钮为 32px；手机普通按钮、小按钮及下拉菜单项统一至少 44px 高。登录控件、图标操作和探索筛选仍有自己的布局规则；这些尺寸不等于已完成全部触屏命中区域验收。

动作名称说明真实后果。“删除任务及文件”先显示含任务名和文件删除说明的确认框，确认后才请求；“强制全部执行”说明将包含今日已成功站点。确认按钮沿用具体动作名称，避免与普通“继续／暂停”混淆。

### Inputs / Fields

标签常显，帮助与错误信息紧邻字段，密码和凭据保持现有脱敏语义。普通输入框最小高度为 40px，手机输入与选择框文字使用 `input-mobile`；聚焦时改变边框并增加主色低透明度光圈，禁用使用次级表面。顶部搜索输入属于组合控件，不能按独立输入框的圆角直接判断。

浅深主题的普通输入与选择框均使用内容表面、正文和边框变量；深色规则显式覆盖旧 Tabler 选择器。占位文字使用完整不透明度的辅助文字色，不再叠加淡化。

长表单按实际保存分区跟踪草稿，动作名称明确范围，底部状态区分别表达未修改、未保存、保存中、已保存与失败。成功只确认提交时的快照；请求期间的后续输入仍为草稿，失败不清空表单。连接测试与保存分开：下载器测试读取已保存配置，存在新修改时先提示保存。

### Cards / Containers

普通卡片保持平面，标题、内容、底部操作区使用一致的边界与间距。内容区通常使用 24px 内边距，手机为 20px；任务行和搜索结果有更紧凑的局部规则。连接器、工具卡 hover 只强调边框，不产生抬升。

下载任务使用 16px 内边距的紧凑任务行，名称、状态、进度与暂停／继续常显；删除保留在更多菜单。名称搜索与状态筛选提供计数、无结果和重置反馈，更新失败时保留已显示结果。签到页以紧凑摘要和今日结果开场，失败／待执行优先；执行策略后置为可折叠分区，保存位于分区底部。

批量暂停／继续通过任务复选框和“选择可见任务”确定范围，筛选隐藏的选择会清除并提示。独立结果区逐项表达等待、执行中、成功、失败和未执行；失败重试只重做结果清单中的失败项。执行期间锁定冲突控制，停止按钮写“停止后续操作”，不暗示取消当前已发请求；切页停止剩余队列。指令成功与刷新后的实际任务状态分别表达，不提供批量删除。

### Navigation

侧栏按当前页显示选中状态，hover、active 与默认文字使用独立固定配色。桌面保留完整侧栏，窄屏改为抽屉；顶部搜索和当前导航继续可用。导航条目圆角与普通按钮不同，不直接把导航视为一组主按钮。

“下载任务”覆盖进行中、暂停和已完成的当前任务；页面名称不再仅指正在传输的状态。签到结果与站点维护可按站点互相定位，使用完整链接保持返回和新标签页能力；定位以高亮与说明呈现，不自动打开编辑表单。

存在未保存分区时，导航与浏览器历史先明确询问是否放弃修改；取消保留当前输入。已跟踪表单的历史项重新请求已保存值，不复用表单 HTML 快照；草稿与密码不写入浏览器存储。离开和关闭编辑层使用不同文案，避免把暂时关闭误认为保存。

### Chips

探索筛选的标签常显，选中使用主色文字与浅强调背景；状态与 `aria-pressed` / `aria-current` 同步。桌面使用紧凑尺寸，手机最小高度为 44px。来源标签以下边线表达当前来源，不引入额外卡片外框。

### Media Cards

海报、片名与元数据始终可见，详情入口和资源搜索分别保留。悬停或键盘聚焦时才显示的摘要是补充信息，不承载唯一的片名或操作。摘要采用 180ms 透明度过渡，减少动态效果时关闭。

**已记录的文档差异：**旧规范允许片名两行，当前媒体卡标题实际单行省略；人物姓名另有两行规则。本次不把单行截断扩大为所有标题的要求。

### Tables, Empty States and Overlays

表格使用次级表面表头、细分隔线与等宽数字，hover 行采用浅强调色。空状态保持简洁标题、解释和对应行动；加载、成功空结果和失败重试分别呈现，不将错误包装成无数据。

资源搜索在桌面和手机均保留明确的“下载”操作；存在详情或种子文件链接时提供“更多”。标题链接用于详情，无详情时显示普通标题。下载弹层保留资源名、可获得的站点／质量／体积，以及自动目录规则；失败在弹层内反馈并保留选择，成功提供“查看下载任务”和“继续浏览”。统计入口的可访问名称包含站点、动作和对应数值，不使用内部标识代替用户语言。

弹窗的默认宽度为 600px，小、大、特大变体分别为 420px、880px、1140px，并受视口限制；消息抽屉最大 440px。长内容在正文区域滚动，动作区保持清楚。

未保存确认使用原生 HTML `dialog`，默认动作是“继续编辑”。离页动作写“放弃修改并离开”；关闭编辑弹窗则说明“关闭并保留本页草稿”，关闭后仍未保存，之后离页仍需确认。提示与操作沿用现有表面、文字和按钮语义，不新增一套配色。

### Focus and Motion

全局焦点当前为 3px 主色描边并偏移 3px；探索来源与筛选控件使用 2px / 2px 的局部规则。输入框另有 3px 低透明度光圈。旧规范的 2px 全局建议与当前实现不同，不能据此声称已统一。

编辑弹窗支持 Esc，脏态由未保存确认保护；退出链式反馈时尽量恢复最初触发控件，入口不可用时聚焦主内容。原生确认和 Bootstrap 模态层协调焦点约束，全局搜索快捷键在弹窗、抽屉或 `dialog` 打开时避让。

优先使用短暂的状态过渡。`prefers-reduced-motion` 下关闭平滑滚动，并把通用动画和过渡压缩至近乎即时；媒体摘要单独关闭过渡。这些是已有行为，不代表已完成全站无障碍审计。

## Do's and Don'ts

### Do:

- **Do** 复用当前主题变量、Jinja 宏和 Lit 组件，新增页面先匹配已有页面族。
- **Do** 保持常显标题、字段标签、状态与主要操作，媒体图片加载前预留面积。
- **Do** 区分加载、无结果与失败，为实际错误提供对应恢复入口。
- **Do** 在浅深主题与窄屏中核对文字、焦点和操作命中区域，保留减少动态效果的行为。

### Don't:

- **Don't** 用营销横幅、装饰性主视觉或普遍浮起的卡片替代管理内容的层级。
- **Don't** 创建第二套近似颜色、字体和控件来绕过现有共享系统。
- **Don't** 只靠 hover 或颜色传达关键内容、选中状态和错误。
- **Don't** 将历史参考图、示例数据、色阶预览或尚未达成的规范目标写成当前生产效果。

以上约束来自当前实现、既有规范与本次确认。文档中的差异用于避免误读，不构成自动修复源码或重写既有规范的指令。
