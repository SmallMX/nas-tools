# Docker 部署

本项目仅支持 Docker Compose 部署。生产镜像由当前工作区源码构建，不依赖预构建的公共镜像，也不在运行中的容器内拉取或更新源码。

> 这是全新项目的数据库基线。首次部署必须使用空的配置目录，不要直接挂载旧 NAS-Tools 项目的 `user.db`。

## 要求

- Docker Engine
- Docker Compose v2（使用 `docker compose` 命令）

## 启动

在仓库根目录执行：

```bash
docker compose -f docker/compose.yml up -d --build
```

首次启动会在持久化配置目录中生成 `config.yaml`、`user.db` 和权限为 `0600` 的 `initial-credentials.txt`。读取初始管理员密码与 API Key：

```bash
docker compose -f docker/compose.yml exec nas-tools cat /config/initial-credentials.txt
```

首次登录并保存凭据后，请删除 `initial-credentials.txt`，避免明文凭据长期留存。

默认访问地址为 `http://localhost:3000`。

## 持久化与运行参数

Compose 支持以下环境变量：

| 变量 | 默认值 | 用途 |
| --- | --- | --- |
| `NASTOOL_CONFIG_DIR` | `./config` | 配置和数据库的宿主机目录 |
| `NASTOOL_MEDIA_DIR` | `./media` | 映射到容器 `/downloads` 的下载数据目录 |
| `NASTOOL_BIND_ADDRESS` | `0.0.0.0` | Web 端口的宿主机绑定地址 |
| `NASTOOL_PORT` | `3000` | Web 的宿主机发布端口 |
| `NASTOOL_IMAGE` | `nas-tools:local` | 本地构建的镜像名 |
| `PUID` / `PGID` | `1000` / `1000` | 容器内运行用户的 UID/GID，需与下载数据目录所有者匹配 |
| `UMASK` | `022` | 新建文件的权限掩码 |
| `NASTOOL_WEB_THREADS` | `8` | Gunicorn 请求线程数；worker 固定为 1，避免重复启动后台任务 |

Gunicorn 在容器内固定监听 `0.0.0.0:3000`。不要在 `config.yaml` 中配置监听地址、端口、TLS 或 Debug；宿主机发布范围只由 `NASTOOL_BIND_ADDRESS` 和 `NASTOOL_PORT` 控制。

示例：

```bash
NASTOOL_CONFIG_DIR=/srv/nas-tools/config \
NASTOOL_MEDIA_DIR=/srv/media \
NASTOOL_BIND_ADDRESS=127.0.0.1 \
docker compose -f docker/compose.yml up -d --build
```

当下载器和 NAS-Tools 需要访问同一目录时，两者必须映射同一个宿主机路径，并使用兼容的 UID/GID，以便检查目录可用空间和浏览下载文件。

启动脚本只会调整 `/downloads` 挂载根目录本身的所有者，不会递归修改已有下载内容。挂载目录中的既有子目录和文件仍须在宿主机上赋予所配置 PUID/PGID 所需的读写权限。

相对卷路径以 `docker/compose.yml` 所在目录为基准，所以默认配置和下载数据目录分别是仓库内的 `docker/config` 与 `docker/media`。`config.yaml`、`user.db` 及配置目录会自动收紧为仅运行用户可读写。

## 反向代理网络

默认会创建名为 `nas-tools` 的 Docker 网络。如需加入已有的外部反向代理网络，同时设置：

```bash
NASTOOL_NETWORK=proxy \
NASTOOL_NETWORK_EXTERNAL=true \
docker compose -f docker/compose.yml up -d --build
```

容器内 Gunicorn 固定提供 HTTP，反向代理上游请使用 `http://nas-tools:3000`。HTTPS 证书与 TLS 终止应配置在反向代理上，不要把证书私钥挂载进应用容器。

通过 HTTPS 对外提供服务时，请在 `config.yaml` 的 `security` 段设置 `session_cookie_secure: true`，使浏览器只通过 HTTPS 发送登录 Session Cookie。仅通过本机 HTTP 访问时保持默认 `false`。

## 更新与回退

更新只通过宿主机源码和镜像重建完成：

```bash
git pull --ff-only
docker compose -f docker/compose.yml up -d --build
```

应用状态全部位于 `NASTOOL_CONFIG_DIR` 指定的目录。更新前停止容器并完整备份该目录。回退时检出目标源码版本、恢复与该版本匹配的配置备份，再重新构建；不要在容器内执行 `git` 或依赖安装命令。
