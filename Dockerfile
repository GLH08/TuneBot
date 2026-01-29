FROM python:3.10-slim

WORKDIR /app

ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 安装编译依赖（用于 tgcrypto）和 Node.js（用于 execjs）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    nodejs \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data /app/logs

CMD ["python", "bot.py"]
