# One image, three roles (ADR-0003, docs/50_cloud_strategy.md).
#
# A single slim Python 3.12 image installs the package and its runtime pins and
# runs the producer, the consumer, or the read-only dashboard, selected by the
# first argument to the entrypoint. The same image serves all three compose
# services locally and on the box, so there is one build and one artifact.
#
# Build for the target box explicitly. The t4g instance is arm64 (Graviton) while
# the build host is x86_64, so the image MUST be built for linux/arm64 or the box
# fails at boot with an exec-format error:
#   docker buildx build --platform linux/arm64 -t <repo>:<tag> --push .
# The runtime wheels (confluent-kafka, pyarrow, pyiceberg-core, duckdb) all ship
# aarch64 manylinux builds, so no compiler or system package is needed.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src

WORKDIR /app

# Runtime pins only (requirements-dev.txt stays out of the image). Copied first so
# the dependency layer caches independently of the source.
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# The package source, the read-only dashboard, and the role dispatcher.
COPY src ./src
COPY app ./app
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# Default to the read-only role. The compose command overrides it per service.
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["dashboard"]
