FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MPLCONFIGDIR=/tmp/matplotlib \
    PRODUCT_CONFIG_DIR=/data/config \
    REPORTS_DIR=/data/reports \
    DATA_DIR=/data \
    PORT=8080 \
    APP_MODE=setup

RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-dejavu-core ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY . /app

WORKDIR /app
RUN pip install --no-cache-dir .

COPY scripts/product-entrypoint.sh /usr/local/bin/product-entrypoint
RUN chmod +x /usr/local/bin/product-entrypoint \
    && mkdir -p /data/config /data/reports /data/runtime

EXPOSE 8080

HEALTHCHECK --interval=15s --timeout=5s --start-period=45s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=3).read()" || exit 1

CMD ["/usr/local/bin/product-entrypoint"]
