FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 MPLCONFIGDIR=/tmp/matplotlib
RUN apt-get update && apt-get install -y --no-install-recommends fonts-dejavu-core ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /bundle
COPY release/chanel_analyzer_bot_product_v0_22_0.tar.gz /bundle/product.tar.gz
RUN tar -xzf /bundle/product.tar.gz --strip-components=1 -C /app && rm /bundle/product.tar.gz
WORKDIR /app
RUN pip install --no-cache-dir .
EXPOSE 8080
ENV APP_MODE=setup PORT=8080 PRODUCT_CONFIG_DIR=/data/config
CMD ["python", "-m", "app.entrypoint"]
