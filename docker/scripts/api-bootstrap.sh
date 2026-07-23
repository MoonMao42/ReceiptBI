#!/bin/sh
set -eu

cd /workspace/apps/api
alembic upgrade head

exec "$@"
