import os

bind = "0.0.0.0:3000"
workers = 1
worker_class = "gthread"
threads = max(1, int(os.environ.get("NASTOOL_WEB_THREADS", "8")))
timeout = 180
graceful_timeout = 60
keepalive = 5
errorlog = "-"
# 只记录不含 query string 的路径，保留可观测性并避免 passkey/token 进入日志。
accesslog = "-"
access_log_format = '%(h)s "%(m)s %(U)s %(H)s" %(s)s %(b)s %(L)s'
control_socket_disable = True

# Docker 内部固定提供 HTTP，TLS 在反向代理层终止，确保上游协议与
# Compose 健康检查一致，并避免将证书私钥放入应用容器。


def worker_exit(_server, _worker):
    """在 Gunicorn worker 退出阶段主动停止后台服务，atexit 仅作兜底。"""
    from run import shutdown_system

    shutdown_system()
