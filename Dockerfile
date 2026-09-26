# Backend image: FastAPI + agent + hybrid search. Data, eval results and model cache are mounted at runtime.
FROM python:3.11-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1
COPY requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt
COPY src/ src/
EXPOSE 8000
CMD ["uvicorn", "main:app", "--app-dir", "src/api", "--host", "0.0.0.0", "--port", "8000"]
