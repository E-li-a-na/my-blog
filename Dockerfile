FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# SQLite 数据文件挂到卷，重建容器不丢数据
ENV DB_PATH=/app/data/blog.db
ENV PORT=8000

EXPOSE 8000
# 监听 Railway 注入的 PORT
CMD ["sh", "-c", "gunicorn -w 2 -b 0.0.0.0:${PORT} app:app"]
