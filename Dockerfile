FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# SQLite 数据文件挂到卷，重建容器不丢数据
VOLUME ["/app/data"]
ENV DB_PATH=/app/data/blog.db

EXPOSE 8000
CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:8000", "app:app"]
