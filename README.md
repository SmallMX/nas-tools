# NAS-Tools

[![CI](https://github.com/SmallMX/nas-tools/actions/workflows/ci.yml/badge.svg)](https://github.com/SmallMX/nas-tools/actions/workflows/ci.yml)
[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](LICENSE.md)

NAS-Tools 是一个面向个人 NAS 的自托管媒体资源检索与下载管理 Web 应用。它将站点搜索、媒体元数据识别、下载器调度、目录选择、任务管理和消息通知串联在一起。

> 当前项目处于 `0.x` 阶段，配置结构和数据库格式仍可能调整。升级前请停止容器并完整备份持久化配置目录。

## 核心功能

| 模块 | 说明 |
|------|------|
| 媒体识别 | 基于 TMDB、Bangumi 和可选的第三方元数据服务识别影视信息与分类 |
| 资源搜索 | 通过内置索引器聚合搜索已配置站点的种子资源 |
| 下载管理 | 对接 qBittorrent 或 Transmission，查看和控制下载任务 |
| 自动下载 | 按媒体类型、二级分类和可用空间选择下载目录 |
| 站点工具 | 提供站点签到、保号登录、刷流任务、失败重试和执行历史 |
| 自动删种 | 按做种时间、分享率、上传量等规则清理下载任务 |
| 消息通知 | 支持 Telegram 通知和交互式搜索 |
| Web 与 API | 提供管理界面和 Swagger API 文档 |

## 部署要求

- Docker Engine 和 Docker Compose v2。
- 媒体识别需要自行申请并配置 TMDB API Key。
- 下载功能需要可访问的 qBittorrent 或 Transmission。
- 应用与下载器需要映射一致的媒体目录，并使用兼容的 `PUID`、`PGID` 权限。
- 本地开发需要 Python 3.14；具体版本约束见 [pyproject.toml](pyproject.toml)。

项目仅支持 Docker Compose 从当前源码构建，不发布或依赖预构建公共镜像，也不支持在容器内更新源码。

## 快速开始

```bash
git clone https://github.com/SmallMX/nas-tools.git
cd nas-tools
NASTOOL_BIND_ADDRESS=127.0.0.1 docker compose -f docker/compose.yml up -d --build
docker compose -f docker/compose.yml exec nas-tools cat /config/initial-credentials.txt
```

访问 `http://localhost:3000`，使用输出的管理员账号和密码登录。保存凭据后删除初始凭据文件：

```bash
docker compose -f docker/compose.yml exec nas-tools rm /config/initial-credentials.txt
```

上面的启动命令只监听本机。如需从局域网访问，可将 `NASTOOL_BIND_ADDRESS` 设置为 NAS 的局域网地址；直接省略时，Compose 默认监听 `0.0.0.0`。

配置和媒体目录默认持久化到 `docker/config` 和 `docker/media`，也可以指定宿主机路径：

```bash
NASTOOL_BIND_ADDRESS=192.168.1.10 \
NASTOOL_CONFIG_DIR=/srv/nas-tools/config \
NASTOOL_MEDIA_DIR=/srv/media \
docker compose -f docker/compose.yml up -d --build
```

更多网络、权限、更新和故障排查说明见 [Docker 部署文档](docker/readme.md)。

## 初始配置

容器内主配置文件固定为 `/config/config.yaml`，首次启动时根据 [配置模板](config/config.example.yaml) 自动创建。主要配置段如下：

| 配置段 | 用途 |
|--------|------|
| `app` | 登录、日志、代理和外部元数据服务凭据 |
| `media` | 媒体二级分类策略 |
| `pt` | 下载器选择、索引站点、搜索策略和任务管理范围 |
| `qbittorrent` | qBittorrent 连接信息 |
| `transmission` | Transmission 连接信息 |
| `tools.site_signin` | 自动签到周期、并发、重试、通知和历史策略 |
| `security` | API Key、Session、Webhook 密钥与来源限制 |
| `downloaddir` | 按媒体类型和二级分类匹配下载目录 |
| `laboratory` | 实验性功能开关 |

TMDB、Fanart 和豆瓣等第三方服务的凭据必须由使用者自行获取并配置；本项目不提供或内置第三方 API Key、账号、Cookie。

## 安全提示

- Compose 默认会把端口发布到 `0.0.0.0`。仅本机使用或通过同机反向代理提供服务时，请设置 `NASTOOL_BIND_ADDRESS=127.0.0.1`。
- 公网访问必须通过 HTTPS 反向代理，并将 `security.session_cookie_secure` 设置为 `true`。
- 不要公开或提交 `config.yaml`、`user.db`、`initial-credentials.txt`、下载器密码、站点 Cookie、API Key 或未经脱敏的日志。
- 首次登录后立即保存生成的凭据，并删除 `initial-credentials.txt`。
- API 默认入口为 `http://localhost:3000/api/v1/`；暴露到不受信任网络前应配置 API Key 和访问控制。

## 数据与升级

当前代码只支持由当前版本首次创建的 `user.db`，不提供旧版 NAS-Tools 数据库的自动迁移。首次部署请使用空的配置目录；升级前应停止容器并备份整个配置目录。

项目不会在容器内拉取或替换源码。更新时在宿主机拉取代码后重新构建：

```bash
git pull --ff-only
docker compose -f docker/compose.yml up -d --build
```

## 开发与验证

```bash
uv sync --locked --no-dev --no-install-project
.venv/bin/python -m compileall -q app web tests config.py check_config.py run.py
.venv/bin/python tests/run.py
docker compose -f docker/compose.yml config --quiet
```

CI 使用相同的锁文件、测试入口和 Compose 定义。测试默认使用临时配置和数据库，不会写入开发环境的 `NASTOOL_CONFIG`。

主要代码入口：

| 路径 | 说明 |
|------|------|
| `run.py` | 应用入口 |
| `app/` | 媒体、站点、下载器、任务和调度等核心业务 |
| `web/` | Flask 路由、API、模板和静态资源 |
| `config/` | 默认配置与内置站点定义 |
| `docker/` | 镜像构建、启动脚本和 Compose 配置 |
| `tests/` | 回归与安全检查 |

## 贡献

提交 Issue 时请附上版本、Docker 环境、复现步骤和脱敏日志；不要上传配置文件、数据库、Cookie 或任何访问凭据。提交 Pull Request 时请说明变更范围、兼容性影响和已完成的验证。

## 使用声明

本项目不提供或分发媒体内容、种子、站点账号、Cookie 或第三方 API 凭据。使用者应确保对检索、下载、整理和分享的内容具有合法权限，并遵守所在地法律、站点规则及第三方服务条款。

本项目与 TMDB、Bangumi、Fanart、豆瓣、Telegram、qBittorrent、Transmission 及相关站点不存在隶属或背书关系。上游来源与第三方归属见 [第三方声明](NOTICE.md)。

This product uses the TMDB API but is not endorsed or certified by TMDB.

## 许可证

本项目是基于上游 AGPL 项目的修改作品，继续采用 [GNU Affero General Public License v3.0](LICENSE.md)（`AGPL-3.0-only`）发布。通过网络向用户提供修改版服务时，应按许可证要求向这些用户提供对应源代码。
