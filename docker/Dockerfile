FROM python:3.14.7-alpine3.23

ARG UV_VERSION=0.11.19

ENV LANG="C.UTF-8" \
    TZ="Asia/Shanghai" \
    NASTOOL_CONFIG="/config/config.yaml" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PS1="\u@\h:\w \$ " \
    PUID=1000 \
    PGID=1000 \
    UMASK=022 \
    WORKDIR="/nas-tools"

ENV PATH="${WORKDIR}/.venv/bin:${PATH}"

WORKDIR ${WORKDIR}

# Install dependencies using local package list
COPY package_list.txt /tmp/package_list.txt

RUN apk add --no-cache $(cat /tmp/package_list.txt) \
    && ln -sf /usr/share/zoneinfo/${TZ} /etc/localtime \
    && echo "${TZ}" > /etc/timezone \
    && ln -sf $(which python3) /usr/bin/python \
    && python3 -m pip install --no-cache-dir "uv==${UV_VERSION}" \
    && rm -rf /tmp/* /root/.cache /var/cache/apk/*

# Copy python dependencies spec
COPY pyproject.toml uv.lock ./

# Install Python dependencies into the image-local project environment.
RUN apk add --no-cache --virtual .build-deps \
        gcc \
        musl-dev \
        libffi-dev \
        libxml2-dev \
        libxslt-dev \
    && uv sync --locked --no-dev --no-install-project \
    && apk del .build-deps \
    && python3 -c "import cffi, gunicorn, lxml.etree" \
    && rm -rf /root/.cache /var/cache/apk/*

# Copy source code
COPY . .

# Setup nas-tools paths
RUN chmod 0755 "${WORKDIR}/config" \
    && python3 -c "from pathlib import Path; import site; Path(site.getsitepackages()[0], 'nas-tools.pth').write_text('${WORKDIR}/\\n')"

EXPOSE 3000
VOLUME ["/config"]
ENTRYPOINT ["/nas-tools/docker/entrypoint.sh"]
