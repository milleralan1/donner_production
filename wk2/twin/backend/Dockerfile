FROM python:3.12-slim

WORKDIR /app

# Install dependencies first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code and data
COPY server.py context.py resources.py ./
COPY data ./data

# Cloud Run sets PORT automatically; default to 8000 for local runs
ENV PORT=8000
EXPOSE 8000

CMD ["python", "server.py"]