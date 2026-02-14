FROM python:3.12-slim

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .

# Create directory for SQLite cache
RUN mkdir -p /data

ENV PORT=8000

# Railway injects its own PORT — use shell form so $PORT gets expanded
CMD uvicorn main:app --host 0.0.0.0 --port $PORT
