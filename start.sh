#!/bin/sh
set -e

# Render Free Web Services require a process listening on $PORT. The Celery
# worker does the actual work; this listener exists solely for platform health
# detection and must not be used as the public API.
python -m http.server "${PORT:-10000}" &

# Replace the shell with Celery so it receives termination signals directly on
# redeploy or shutdown rather than leaving an orphan worker behind.
exec uv run celery -A src.system_design.setup.celery_app.celery_instance worker --loglevel=info --pool=solo
