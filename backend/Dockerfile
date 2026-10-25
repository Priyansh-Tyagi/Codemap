# syntax=docker/dockerfile:1
# CodeMap API image. Build context is backend/ :  docker build -t codemap-api:dev backend
#
# NOT yet built on a real Docker daemon by the author of this file (the sandbox had none);
# the entrypoint/Litestream logic WAS exercised for real - see docker/e2e_replication.py.

# ---- stage 1: parser dependencies (npm never reaches the runtime image) ----------------
FROM node:22-bookworm-slim AS parser-deps
WORKDIR /build
COPY parser/package.json parser/package-lock.json ./
RUN npm ci --omit=dev

# ---- stage 2: fetch + VERIFY the Litestream binary --------------------------------------
# Pinned by version AND sha256, same supply-chain stance as requirements.lock.
FROM debian:bookworm-slim AS litestream
ARG LITESTREAM_VERSION=0.5.17
ARG LITESTREAM_SHA256=cfb371176d164437ae869f8351cfde49bd1804ae71c61923f75c9cba9c9c006d
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl \
 && curl -fsSL -o /tmp/ls.tgz \
      "https://github.com/benbjohnson/litestream/releases/download/v${LITESTREAM_VERSION}/litestream-${LITESTREAM_VERSION}-linux-x86_64.tar.gz" \
 && echo "${LITESTREAM_SHA256}  /tmp/ls.tgz" | sha256sum -c - \
 && tar -xzf /tmp/ls.tgz -C /usr/local/bin litestream

# ---- stage 3: runtime -------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

# Same Debian release as the node image, so the copied binary's glibc matches.
COPY --from=parser-deps /usr/local/bin/node /usr/local/bin/node
COPY --from=litestream /usr/local/bin/litestream /usr/local/bin/litestream
# Fail the BUILD (not the first request) if either binary cannot run here
# (e.g. a missing shared library: add `apt-get install libstdc++6`).
RUN node --version && litestream version

WORKDIR /srv/codemap
# Dependencies first: editing app code must not reinstall them (layer cache).
COPY requirements.lock ./
RUN pip install --require-hashes -r requirements.lock

# Layout is load-bearing: the parser bridge finds ../../parser/parse.js relative to
# app/analyzer, and modules import as top-level names, so uvicorn runs from app/.
COPY app ./app
COPY parser/package.json parser/parse.js ./parser/
COPY --from=parser-deps /build/node_modules ./parser/node_modules
COPY docker ./docker

# Non-root. /data is created here and owned by this user, so a *named volume*
# (which copies this ownership on first use) is writable too.
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin codemap \
 && mkdir -p /data && chown codemap:codemap /data \
 && chmod +x docker/entrypoint.sh

# Secure-by-default values; secrets are injected at RUN time, never baked in.
# CODEMAP_PARSER_MAX_HEAP_MB: Node's heap must stay well under the container's RAM, so a
# huge repo becomes a handled "parser failed" error instead of an OOM kill that skips
# the final backup. 192 MB suits a 512 MB container shared with Python + Litestream.
ENV CODEMAP_DB_PATH=/data/codemap.db \
    CODEMAP_ALLOW_LOCAL_PATHS=false \
    CODEMAP_DISABLE_DOCS=true \
    CODEMAP_PARSER_MAX_HEAP_MB=192 \
    PORT=8000

USER codemap
VOLUME /data
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
  CMD ["python", "/srv/codemap/docker/healthcheck.py"]
ENTRYPOINT ["/srv/codemap/docker/entrypoint.sh"]
