############################################################
# Build the OpenSearch MCP Server (opensearch-mcp-server-py) Docker image
############################################################

ARG PYTHON_IMAGE=python:3.12-slim-trixie@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b

FROM ghcr.io/astral-sh/uv:0.13.7@sha256:96f40d3904aad8d0bd010539001d36c8e2188b981e1334471a90c4a1d93bb490 AS uv

#
# Stage 1: build the wheel and export locked, hashed requirements from uv.lock
#
FROM ${PYTHON_IMAGE} AS build-stage

COPY --from=uv /uv /usr/local/bin/uv

WORKDIR /build
COPY pyproject.toml uv.lock README.md LICENSE.txt NOTICE.txt ./
COPY src/ src/

RUN uv export --frozen --no-dev --no-emit-project --format requirements.txt --output-file requirements.txt && \
    uv build --wheel --out-dir dist

#
# Stage 2: create image
#
FROM ${PYTHON_IMAGE} AS image-stage

RUN groupadd --gid 1000 opensearch && \
    useradd --uid 1000 --gid 1000 --no-create-home --shell /usr/sbin/nologin opensearch

COPY --from=build-stage /build/requirements.txt /build/dist/*.whl /tmp/install/

RUN pip install --no-cache-dir --disable-pip-version-check --require-hashes -r /tmp/install/requirements.txt && \
    pip install --no-cache-dir --disable-pip-version-check --no-deps /tmp/install/*.whl && \
    rm -rf /tmp/install

USER 1000

ARG VERSION
ARG BUILD_DATE
LABEL org.label-schema.schema-version="1.0" \
      org.label-schema.vendor="OpenSearch-Project" \
      org.label-schema.name="opensearch-mcp-server-py" \
      org.label-schema.url="https://opensearch.org/" \
      org.label-schema.version="$VERSION" \
      org.label-schema.license="Apache-2.0" \
      org.label-schema.description="OpenSearch MCP Server" \
      org.label-schema.build-date="$BUILD_DATE" \
      org.label-schema.vcs-url="https://github.com/opensearch-project/opensearch-mcp-server-py" \
      org.opencontainers.image.title="opensearch-mcp-server-py" \
      org.opencontainers.image.version="$VERSION" \
      org.opencontainers.image.licenses="Apache-2.0" \
      org.opencontainers.image.source="https://github.com/opensearch-project/opensearch-mcp-server-py"

ENTRYPOINT ["opensearch-mcp-server-py"]
