FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

ENV UV_PROJECT_ENVIRONMENT="/venv"

ENV UV_LINK_MODE=copy

# 1. 安装基础工具 + OpenSSH Server
# mkdir /var/run/sshd 是 sshd 启动需要的目录
RUN apt-get update && apt-get install -y \
    ca-certificates \
    git \
    curl \
    openssh-server \
    supervisor \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /var/run/sshd

# 2. 配置 SSH root 账户密码
RUN echo 'root:root' | chpasswd && \
    sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin yes/' /etc/ssh/sshd_config

# 3. 安装 uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# 4. 设置工作目录
WORKDIR /workspace

# 5. 预先配置 Python 环境
COPY pyproject.toml uv.lock ./

RUN uv sync --frozen

# 6. SSH 端口 + 应用端口
EXPOSE 22 8080

# 7. 前台启动 SSH 服务
CMD ["/usr/sbin/sshd", "-D"]