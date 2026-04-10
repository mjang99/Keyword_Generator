FROM mcr.microsoft.com/playwright/python:v1.58.0-noble

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    PYTHONUTF8=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    XDG_CACHE_HOME=/tmp \
    HOME=/tmp

WORKDIR /var/task

RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir \
        awslambdaric \
        boto3 \
        botocore \
        crawl4ai==0.8.0 \
        playwright==1.58.0

COPY pyproject.toml ./pyproject.toml
COPY src ./src

ENTRYPOINT ["/usr/bin/python3", "-m", "awslambdaric"]
CMD ["src.handlers.workers.collection_worker_handler"]
