FROM python:3.11-slim

WORKDIR /app

# ModelScope 创空间要求应用监听 7860 端口
ENV PYTHONUNBUFFERED=1 \
    PORT=7860 \
    OPENAI_API_KEY=c39c5e7be0c644c18fb09cfee159a5a0.3OqCQcrYtjoQTVE8 \
    OPENAI_BASE_URL=https://open.bigmodel.cn/api/paas/v4 \
    OPENAI_MODEL=glm-5.3-flash

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/

COPY . .

EXPOSE 7860

CMD ["python", "server.py"]
