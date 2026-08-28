#1.使用ubuntu基础镜像来源
FROM ubuntu:22.04

#2.安装过程中避免交互式提示并设置主机名
ENV DEBIAN_FRONTEND=noninteractive
ENV HOSTNAME=sandbox

#3.先用阿里云HTTP源安装证书，再升级为HTTPS源
RUN sed -i 's|http://archive.ubuntu.com/ubuntu/|http://mirrors.aliyun.com/ubuntu/|g' /etc/apt/sources.list && \
    sed -i 's|http://security.ubuntu.com/ubuntu/|http://mirrors.aliyun.com/ubuntu/|g' /etc/apt/sources.list && \
    sed -i 's|http://ports.ubuntu.com/ubuntu-ports/|http://mirrors.aliyun.com/ubuntu-ports/|g' /etc/apt/sources.list && \
    apt-get update && \
    apt-get install -y ca-certificates && \
    update-ca-certificates && \
    sed -i 's|http://mirrors.aliyun.com/ubuntu/|https://mirrors.aliyun.com/ubuntu/|g' /etc/apt/sources.list && \
    sed -i 's|http://mirrors.aliyun.com/ubuntu-ports/|https://mirrors.aliyun.com/ubuntu-ports/|g' /etc/apt/sources.list

#4.跟新和安装基础软件后移除依赖
RUN apt-get update && apt-get install -y \
    sudo bc curl wget gnupg software-properties-common supervisor \
    xterm socat xvfb x11vnc websockify \
    xz-utils \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* 

#5.创建ubuntu用户并且赋予sudo权限
RUN useradd -m -d /home/ubuntu -s /bin/bash ubuntu && \
    echo "ubuntu ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/ubuntu

#6.安装Python 3.10
RUN add-apt-repository ppa:deadsnakes/ppa && \
    apt-get update && \
    apt-get install -y \
    python3.10 \
    python3.10-venv \
    python3.10-dev \
    python3-pip && \
    update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.10 1 &&\
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* 


#7.为pip3配置阿里云镜像源
RUN pip3 config set global.index-url https://mirrors.aliyun.com/pypi/simple/

# 8.安装 Node.js 24.12.0 LTS
RUN ARCH=$(dpkg --print-architecture) && \
    if [ "$ARCH" = "amd64" ]; then NODE_ARCH="x64"; \
    elif [ "$ARCH" = "arm64" ]; then NODE_ARCH="arm64"; \
    else echo "Unsupported architecture: $ARCH" && exit 1; fi && \
    wget https://nodejs.org/dist/v24.12.0/node-v24.12.0-linux-${NODE_ARCH}.tar.xz && \
    tar -xJf node-v24.12.0-linux-${NODE_ARCH}.tar.xz -C /usr/local --strip-components=1 && \
    rm node-v24.12.0-linux-${NODE_ARCH}.tar.xz && \
    node --version && \
    npm --version

#9.将npm镜像源设置为阿里云镜像源
RUN npm config set registry https://registry.npmmirror.com


#10.安装Google chrome浏览器
RUN add-apt-repository ppa:xtradeb/apps -y && \
    apt-get update && \
    apt-get install -y chromium --no-install-recommends && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

#11.安装中文字体和语言支持
RUN apt-get update && apt-get install -y \
    fonts-noto-cjk \
    fonts-noto-color-emoji \
    language-pack-zh-hans \
    locales \
    && locale-gen zh_CN.UTF-8 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

#12.设置默认编码
ENV LANG=zh_CN.UTF-8 \
    LANGUAGE=zh_CN:zh \
    LC_ALL=zh_CN.UTF-8

#13.设置工作空间
WORKDIR /sandbox

#14.拷贝项目依赖文件到工作空间并安装依赖
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

#15.拷贝整个项目文件
COPY . .
#16.将supervisord.config拷贝到supervisor服务的配置目录中

#17.暴露端口 8080(FastAPI) 9222(CDP) 5900(VNC) 5901(Websocket)
EXPOSE 8080 9222 5900 5901
#18.额外的环境变量配置
ENV CHROME_ARGS=""
ENV UVI_ARGS=""

#19.使用supervisor管理所有进程
CMD ["supervisord", "-n", "-c", "/sandbox/supervisord.conf"]
