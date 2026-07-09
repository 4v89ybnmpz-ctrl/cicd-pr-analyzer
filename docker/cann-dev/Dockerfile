FROM ubuntu:latest

LABEL description="CANNBot Ascend C 算子开发 Docker 环境（含 Claude Code CLI）"

# 避免交互式安装
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Asia/Shanghai

# ===== 系统构建工具 + Node.js =====
RUN apt-get update && apt-get install -y --no-install-recommends \
    cmake \
    g++ \
    gcc \
    make \
    git \
    curl \
    wget \
    ca-certificates \
    gnupg \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    vim \
    sudo \
    && rm -rf /var/lib/apt/lists/*

# 软链接 python → python3
RUN ln -sf /usr/bin/python3 /usr/bin/python

# ===== Node.js 22 + Claude Code CLI =====
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*
RUN npm install -g @anthropic-ai/claude-code

# ===== CANN Toolkit 安装（通过 build-arg 传入 .run 安装包路径或 URL） =====
# 用法:
#   docker build --build-arg CANN_PACKAGE=./Ascend-cann-toolkit_8.0.RC1_linux-x86_64.run \
#                -t cann-dev:8.0.RC1 .
#   若 CANN_PACKAGE 为空则跳过 CANN 安装，后续可挂载宿主机 CANN 目录
ARG CANN_PACKAGE=""
ARG ASCEND_BASE=/usr/local/Ascend

ENV ASCEND_HOME_PATH=${ASCEND_BASE}/ascend-toolkit/latest
ENV PATH=${ASCEND_HOME_PATH}/compiler/bin:${PATH}
ENV LD_LIBRARY_PATH=${ASCEND_HOME_PATH}/lib64:/usr/local/lib
ENV PYTHONPATH=${ASCEND_HOME_PATH}/python/site-packages

COPY install_cann.sh /tmp/install_cann.sh
# COPY 本地 CANN .run 进镜像安装（由 --build-arg CANN_PACKAGE=./Ascend-cann-toolkit_xxx.run 传入）
COPY ${CANN_PACKAGE} /tmp/cann_installer.run
RUN chmod +x /tmp/install_cann.sh && \
    /tmp/install_cann.sh /tmp/cann_installer.run "${ASCEND_BASE}" && \
    rm -f /tmp/install_cann.sh /tmp/cann_installer.run

# ===== 非 root 用户（Claude Code CLI 禁止 root 下 --dangerously-skip-permissions） =====
# 注意：先 COPY + chmod 完成后，再切到非 root 用户
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh && \
    (id ubuntu >/dev/null 2>&1 && userdel -r ubuntu 2>/dev/null || true) && \
    useradd -u 1000 -m -s /bin/bash cann && echo 'cann ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers

RUN apt-get update && apt-get install -y --no-install-recommends sudo && rm -rf /var/lib/apt/lists/*
USER cann

# ===== 算子开发工作目录 =====
WORKDIR /workspace

ENTRYPOINT ["/entrypoint.sh"]
CMD ["bash"]
