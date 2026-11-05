# DRAFT: not yet built (no Docker on the dev machine); built in the cloud with `az acr build`, see documentation/deployment.md
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/opt/hf \
    HOST=0.0.0.0 \
    PORT=7860 \
    CSCLBOT_LOG_DIR=/mnt/state/logs \
    CSCLBOT_USAGE_FILE=/mnt/state/usage.json

WORKDIR /app

# CPU-only PyTorch first (the default wheel bundles CUDA libraries the app never uses)
RUN pip install torch==2.10.0 --index-url https://download.pytorch.org/whl/cpu
COPY requirements-app.txt .
RUN pip install -r requirements-app.txt

# Bake the embedding model into the image so the app never downloads it at runtime
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('intfloat/e5-base-v2')"
ENV HF_HUB_OFFLINE=1

# Only what the running app needs
COPY src/app.py src/answer.py src/search.py src/limits.py src/usage_log.py src/index_common.py ./src/
# GeoLite2-Country.mmdb is optional: the glob copies it only if it exists next to references.json
COPY data/references.json data/GeoLite2-Country.mm[d]b ./data/
COPY data/index ./data/index

RUN useradd --create-home --uid 1000 app && mkdir -p /mnt/state && chown -R app /app /mnt/state /opt/hf
USER app

EXPOSE 7860
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:7860/', timeout=4)"
CMD ["python", "src/app.py"]
