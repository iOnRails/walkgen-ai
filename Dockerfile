FROM python:3.12-slim

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .

# Remove any cached bytecode
RUN find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

# Create directory for SQLite cache
RUN mkdir -p /data

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
