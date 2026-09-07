# Clowdy backend image. One image, two roles.
#
# The control plane and the worker share all their code -- the worker is just
# the execution half of it with an HTTP door on the front. Building one image
# means a single artifact to push, scan, and version, and it makes it
# impossible for the two halves to drift out of sync.
#
#   control plane:  uvicorn app.main:app        --port 8000
#   worker:         uvicorn app.worker.main:app --port 9000
#
# Build from the backend/ directory:
#   docker build -t clowdy-backend backend/

FROM python:3.12-slim

# Never write .pyc files or buffer stdout -- both only hurt inside a container,
# where the filesystem is ephemeral and logs are read from the stream.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/srv

WORKDIR /srv

# Dependencies first, in their own layer. Application code changes on every
# commit; this layer changes only when requirements.txt does, so rebuilds
# skip the slow pip install almost every time.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini .
COPY alembic ./alembic
COPY app ./app

# Run as a non-root user. The worker still reaches the Docker socket through
# the mounted group, so nothing here needs root.
RUN useradd --create-home --uid 10001 clowdy && chown -R clowdy /srv
USER clowdy

EXPOSE 8000 9000

# Overridden per role in docker-compose.yml.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
