#!/bin/sh

set -eu

cd "${WORKDIR}"
umask "${UMASK}"

echo "以PUID=${PUID}，PGID=${PGID}的身份启动程序..."

mkdir -p /config/.cache
chown -R "${PUID}":"${PGID}" /config
if [ -d /downloads ]; then
    chown "${PUID}":"${PGID}" /downloads
fi
for sensitive_file in \
    /config/config.yaml \
    /config/initial-credentials.txt \
    /config/user.db \
    /config/user.db-wal \
    /config/user.db-shm; do
    if [ -f "${sensitive_file}" ]; then
        chmod 600 "${sensitive_file}"
    fi
done

export PATH="${PATH}:/usr/lib/chromium"
export HOME=/config
export XDG_CACHE_HOME=/config/.cache
exec su-exec "${PUID}":"${PGID}" "$(which dumb-init)" \
    "$(which gunicorn)" --config /nas-tools/docker/gunicorn.conf.py run:App
