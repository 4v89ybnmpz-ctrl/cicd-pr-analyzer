FROM python:3.11-slim

WORKDIR /app

# 安装系统依赖（Playwright 需要的系统库）
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    gnupg \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY app/ ./app/

# 复制示例配置文件作为默认配置（用户通过挂载覆盖）
COPY config.example.json ./config.json
COPY encryption_key.example.json ./encryption_key.json

# 创建日志和数据目录
RUN mkdir -p logs data secrets

# 暴露端口
EXPOSE 1234

# 启动命令
CMD ["python", "-m", "app.main"]
