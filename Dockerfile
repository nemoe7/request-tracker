FROM python:3.13-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.12.21 /uv /bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY pwedepa ./pwedepa
RUN uv sync --locked --no-dev --no-cache

FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PWEDEPA_HOST=0.0.0.0 \
    PWEDEPA_PORT=5000 \
    PWEDEPA_DB=/data/pwedepa.db \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app
COPY --from=build /app/.venv /app/.venv
# The venv holds an editable install that points at this folder, so the app
# must sit beside it or every start fails to find the package.
COPY pwedepa ./pwedepa
COPY domains.yaml ./
RUN rm -rf /usr/local/lib/python3.13/site-packages/pip \
      /usr/local/lib/python3.13/site-packages/pip-*.dist-info \
      /usr/local/lib/python3.13/site-packages/setuptools \
      /usr/local/lib/python3.13/site-packages/setuptools-*.dist-info \
      /usr/local/lib/python3.13/ensurepip \
      /usr/local/bin/pip /usr/local/bin/pip3 \
    && useradd --system pwedepa \
    && mkdir -p /data \
    && chown pwedepa /data

USER pwedepa
EXPOSE 5000
CMD ["python", "-m", "pwedepa.web"]
