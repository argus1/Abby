FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/workspace/src

WORKDIR /workspace

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY . /workspace

RUN python -m pip install --upgrade pip \
    && python -m pip install -e .[dev]

EXPOSE 8000

CMD ["uvicorn", "abby_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
