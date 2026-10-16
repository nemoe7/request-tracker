FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PWEDEPA_HOST=0.0.0.0 \
    PWEDEPA_PORT=5000 \
    PWEDEPA_DB=/data/pwedepa.db

WORKDIR /app
COPY pyproject.toml ./
COPY pwedepa ./pwedepa
RUN pip install --no-cache-dir . \
    && pip install --no-cache-dir --upgrade pip setuptools \
    && rm -rf /usr/local/lib/python3.13/ensurepip \
    && useradd --system pwedepa \
    && mkdir -p /data \
    && chown pwedepa /data

USER pwedepa
EXPOSE 5000
CMD ["python", "-m", "pwedepa.web"]
