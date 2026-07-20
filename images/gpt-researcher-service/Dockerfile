# syntax=docker/dockerfile:1.7
ARG PYTHON_IMAGE=python:3.12.13-slim-bookworm@sha256:d50fb7611f86d04a3b0471b46d7557818d88983fc3136726336b2a4c657aa30b

FROM ${PYTHON_IMAGE} AS wheels
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore
RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip wheel \
      --wheel-dir /wheels \
      --prefer-binary \
      gpt-researcher==0.16.0

FROM ${PYTHON_IMAGE}
ARG GPT_RESEARCHER_VERSION=0.16.0
ARG SOURCE_REVISION=5d84d2f5553e70a2765a8ff3a0d2672d60437ce8
LABEL org.opencontainers.image.title="Authenticated GPT Researcher service" \
      org.opencontainers.image.description="A minimal internal OpenAPI boundary around GPT Researcher" \
      org.opencontainers.image.source="https://github.com/rezanmz/home-server" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.version="${GPT_RESEARCHER_VERSION}" \
      org.opencontainers.image.revision="${SOURCE_REVISION}"

ENV HOME=/tmp \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore

# Markdown research with the BeautifulSoup scraper does not need a browser.
# libmagic is required by GPT Researcher's document-type dependency graph.
# Python and libmagic do not use Debian's Essential minimal Perl runtime.
# Remove it from this single-purpose image because Bookworm's current
# perl-base contains unfixed Socket/IO::Uncompress vulnerabilities.
RUN apt-get update \
    && apt-get install --yes --no-install-recommends ca-certificates libmagic1 \
    && dpkg --purge --force-remove-essential perl-base \
    && test ! -e /usr/bin/perl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=wheels /wheels /wheels
# GPT Researcher 0.16.0/v3.6.0 publishes query_processing.py with its
# typing import below the first annotated function. Python evaluates the
# annotation during import and raises NameError. Keep the security-fixed
# release and apply the smallest possible import-order repair.
RUN python -m pip install \
      --no-cache-dir \
      --no-index \
      --find-links /wheels \
      "gpt-researcher==${GPT_RESEARCHER_VERSION}" \
    && sed -i '1i from typing import Any, List, Dict' \
      /usr/local/lib/python3.12/site-packages/gpt_researcher/actions/query_processing.py \
    && rm -rf /wheels \
    && groupadd --gid 10001 researcher \
    && useradd --uid 10001 --gid researcher --no-create-home researcher \
    && mkdir -p /app /tmp/research-service \
    && chown -R researcher:researcher /app /tmp/research-service

WORKDIR /app
COPY --chown=researcher:researcher research_service /app/research_service

USER 10001:10001
EXPOSE 8000
ENTRYPOINT ["python", "-m", "uvicorn"]
CMD ["research_service.api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log"]
