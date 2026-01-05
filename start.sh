#!/usr/bin/env bash
set -o errexit

# Render sets $PORT; locally it may be empty
PORT="${PORT:-8000}"

python -m gunicorn config.wsgi:application --bind "0.0.0.0:${PORT}"
