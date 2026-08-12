FROM python:3.13-slim

ARG APP_VERSION=2.7.0
ARG VCS_REF=""
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    RADAR_BUILD_COMMIT="${VCS_REF}"

LABEL org.opencontainers.image.title="Software Release Radar" \
      org.opencontainers.image.description="Self-hosted software release monitoring and upgrade review dashboard" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.licenses="AGPL-3.0-only" \
      org.opencontainers.image.source="https://github.com/muhdusama/Software-Release-Radar"

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates openssh-client \
 && rm -rf /var/lib/apt/lists/* \
 && groupadd --system radar \
 && useradd --system --gid radar --home-dir /app --no-create-home radar \
 && mkdir -p /data /ssh \
 && chown -R radar:radar /data /ssh

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=radar:radar radar ./radar

USER radar

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=8s --retries=3 --start-period=20s \
  CMD python -c "import json,urllib.request; d=json.load(urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=5)); assert d.get('status') == 'ok'" || exit 1

CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--threads", "4", "--timeout", "180", "--access-logfile", "-", "--error-logfile", "-", "radar.application:create_app()"]
