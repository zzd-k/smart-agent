FROM python:3.11-slim

WORKDIR /app

# ModelScope 创空间要求应用监听 7860 端口
ENV PYTHONUNBUFFERED=1 \
    PORT=7860

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/

COPY . .

EXPOSE 7860

CMD ["python", "server.py"]
