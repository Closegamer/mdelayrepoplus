FROM python:3.12-slim
WORKDIR /app
# Нестабильная сеть / слабый VPS: длинные таймауты и много повторов при скачивании с PyPI
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
ENV PIP_DEFAULT_TIMEOUT=1200
COPY requirements.txt .
RUN pip install --upgrade pip setuptools wheel \
    && pip install \
      --retries 30 \
      --default-timeout=1200 \
      --prefer-binary \
      --no-cache-dir \
      -r requirements.txt
COPY . .
