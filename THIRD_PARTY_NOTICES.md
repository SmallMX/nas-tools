# 第三方开源声明

本文件记录仓库中直接包含、改编或以源码形式分发的主要第三方组件。依赖管理器安装的 Python 包仍受各自许可证约束；完整依赖版本见 `uv.lock`。

## NAStool

- 来源：<https://github.com/NAStool/nas-tools>
- 导入版本：v2.9.2
- 许可证：GNU Affero General Public License v3.0 (`AGPL-3.0-only`)
- 范围：项目主体的上游实现

原始部分的版权归 NAStool 原作者及贡献者所有。本项目对上游代码进行了持续修改，修改后的整体继续使用 AGPL-3.0-only。

## MoviePilot

- 来源：<https://github.com/jxxghp/MoviePilot>
- 固定 revision：`96ef431efc535caa4e0cc1203713efea0db74a0c`
- 许可证：GNU General Public License v3.0
- 范围：`config/sites/moviepilot-v2.yml` 以及与该站点定义适配相关的实现

MoviePilot 的 GPL-3.0 条款继续适用于对应部分；根据 GPLv3 与 AGPLv3 的兼容条款，组合后的项目整体按 AGPL-3.0-only 提供。

## tmdbv3api

- 来源：<https://github.com/AnthonyBloomer/tmdbv3api>
- 作者：Anthony Bloomer
- 许可证：MIT
- 范围：`app/media/tmdbv3api/`

MIT License

Copyright (c) Anthony Bloomer

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

## Apache ECharts

- 来源：<https://github.com/apache/echarts/tree/5.3.3>
- 版本：5.3.3
- 许可证：Apache License 2.0
- 范围：`web/static/js/echarts.min.js`

Apache ECharts
Copyright 2017-2022 The Apache Software Foundation

This product includes software developed at the Apache Software Foundation (<https://www.apache.org/>). The bundled file retains its upstream license header; the Apache License 2.0 is available at <https://www.apache.org/licenses/LICENSE-2.0>.

## Lit

- 来源：<https://github.com/lit/lit>
- 许可证：BSD-3-Clause
- 范围：`web/static/components/utility/lit-core.min.js`

该文件保留了 Google LLC 的原始版权、许可证和 SPDX 标识。

## Tabler 与前端库

仓库还包含 Tabler、Bootstrap、Ace、jQuery、FileSaver.js、Dropzone、List.js、NProgress、Numeral.js、jQuery File Tree 等前端库。其上游版权与许可证声明在对应文件头中保留；重新分发或替换这些文件时不得移除原始声明。
