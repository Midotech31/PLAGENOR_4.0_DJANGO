FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ca-certificates curl default-jre-headless gettext libreoffice-writer \
    && install -d /usr/share/postgresql-common/pgdg \
    && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
       -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
    && . /etc/os-release \
    && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt ${VERSION_CODENAME}-pgdg main" \
       > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client-18 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt ./
RUN python -m pip install --upgrade pip && pip install -r requirements.txt
RUN groupadd --gid 10001 plagenor \
    && useradd --uid 10001 --gid plagenor --create-home \
       --home-dir /home/plagenor --shell /usr/sbin/nologin plagenor
COPY --chown=plagenor:plagenor . .
RUN django-admin compilemessages

RUN chmod 0755 /app/docker-entrypoint.sh \
    && mkdir -p /app/data /app/media /app/staticfiles \
    && chown -R plagenor:plagenor /app/data /app/media /app/staticfiles

USER plagenor

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.getenv('PORT','8000')+'/healthz', timeout=3)" || exit 1

CMD ["/app/docker-entrypoint.sh"]
