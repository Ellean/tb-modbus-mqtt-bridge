FROM python:3.11-alpine

LABEL maintainer="Ellean"
LABEL description="Lightweight Modbus to MQTT Bridge using pymodbus"

# 安装必要的构建依赖
RUN apk add --no-cache \
    gcc \
    musl-dev \
    linux-headers \
    && rm -rf /var/cache/apk/*

WORKDIR /app

# 复制依赖文件
COPY requirements.txt .

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt \
    && pip cache purge

# 复制源代码
COPY src/ ./src/

# 创建配置目录
RUN mkdir -p /app/config

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD ps aux | grep -q '[p]ython -m src.main' || exit 1

# 环境变量
ENV CONFIG_DIR=/app/config \
    MQTT_CONFIG=/app/config/mqtt_config.json \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    LOG_LEVEL=INFO

# 非 root 用户
RUN addgroup -g 1000 appuser && \
    adduser -D -u 1000 -G appuser appuser && \
    chown -R appuser:appuser /app

USER appuser

CMD ["python", "-m", "src.main"]