FROM python:3.13-slim

WORKDIR /app

# Install OS libraries for OpenCV and ReportLab
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-train.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Worker images that run MODEL_TRAINING jobs are built with --build-arg TRAINING=true
ARG TRAINING=false
RUN if [ "$TRAINING" = "true" ]; then \
        pip install --no-cache-dir --retries 10 --timeout 120 --index-url https://download.pytorch.org/whl/cpu torch torchvision && \
        pip install --no-cache-dir --no-deps "ultralytics>=8.3" && \
        pip install --no-cache-dir -r requirements-train.txt ; \
    fi

COPY . .

RUN useradd --create-home --uid 10001 app && mkdir -p /app/storage && chown -R app:app /app
USER app
ENV YOLO_CONFIG_DIR=/app/storage/.ultralytics

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=40s --retries=5 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/api/health', timeout=4).status == 200 else 1)"

# The same image runs the API (default), the worker (python -m app.workers.worker)
# and the edge node (uvicorn app.edge.main:app).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
