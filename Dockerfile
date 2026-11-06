FROM python:3.10-slim AS builder

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src/ src/
RUN pip install --no-cache-dir --prefix=/install .

FROM python:3.10-slim

RUN groupadd -g 1000 opensearch && \
    useradd -u 1000 -g 1000 -s /sbin/nologin -M opensearch

COPY --from=builder --chown=1000:1000 /install /usr/local

USER opensearch
ENTRYPOINT ["opensearch-mcp-server-py"]
