# Racik — containerised for Render, AWS App Runner, or any container host
# that injects a $PORT env var and runs a plain Docker image.
#
# Builds racik.db from the raw corpus at IMAGE BUILD TIME, not at container
# start, so cold starts don't pay the ~20s ETL cost. The corpus is a static
# snapshot (see racik/README.md's "Honest limitations"), so baking it in is
# the right trade-off, not a shortcut.
#
# KNOWN LIMITATION: racik_state.db (operator reviews, menu history, stock
# records — everything statedb.py owns) lives on the container's local
# filesystem. That's fine for a single-instance demo, but it will NOT
# persist across a redeploy/restart and will NOT be shared if App Runner
# scales to multiple instances. Moving that store to RDS/DynamoDB is the
# real production fix; out of scope for this build.

FROM python:3.12-slim AS base

WORKDIR /app

# System deps: ortools' Python wheel is self-contained, but pandas/openpyxl
# pull in a couple of C-extension deps that benefit from an up-to-date libstdc++.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY racik/requirements.txt racik/requirements.txt
RUN pip install --no-cache-dir -r racik/requirements.txt boto3

# Backend package, data, scripts, docs.
COPY racik/racik racik/racik
COPY racik/scripts racik/scripts
COPY racik/data racik/data
COPY racik/docs racik/docs
COPY racik/ui racik/ui

# The styled operator frontend, served from the repo root (see
# racik/racik/config.py's FRONTEND_DIR and racik/racik/api.py's static mounts).
COPY index.html index.html
COPY css css
COPY js js
COPY assets assets

# One-time ETL: raw xlsx/csv/json -> racik/data/racik.db (~20-30s).
RUN python racik/scripts/build_db.py

ENV PYTHONUNBUFFERED=1
# Render/App Runner both inject PORT; default to 8000 for `docker run -p 8000:8000` locally.
ENV PORT=8000
EXPOSE 8000

# Shell form so $PORT expands; --app-dir puts racik/ on sys.path without a
# separate `cd`, matching the local .claude/launch.json dev config.
CMD uvicorn --app-dir racik racik.api:app --host 0.0.0.0 --port ${PORT}
