# TerraSight API — FastAPI + rasterio/GDAL.
#
# rasterio and pyproj ship manylinux wheels that bundle GDAL and PROJ, so a slim
# Python base needs no system GDAL — which is exactly why the raster service is
# containerised rather than run as a Vercel function.

FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencies first for layer caching.
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY app ./app

# Run as a non-root user.
RUN useradd --create-home --uid 10001 terrasight
USER terrasight

EXPOSE 8000

# Render (and most PaaS) inject $PORT; fall back to 8000 locally.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
