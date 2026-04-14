FROM python:3.12-slim
WORKDIR /app
ENV PIP_DEFAULT_TIMEOUT=600
COPY requirements.txt .
RUN pip install --retries 15 --no-cache-dir -r requirements.txt
COPY . .
