#!/bin/bash

# =============================================================
# sync-to-host.sh — push the blog repo to the live host and rebuild
#
#   ./infra/sync-to-host.sh [user@host]        sync only
#   ./infra/sync-to-host.sh --deploy [host]    sync, rebuild, restart
#
# Mirrors semprini-core/infra/sync-to-host.sh. The host is not a git checkout;
# code flows laptop -> host by rsync.
#
# Secrets, uploaded media and the database do NOT flow. The host is
# authoritative for all three, and pushing the laptop's copies over them would
# revert rotated credentials or clobber live data.
#
# The image installs Python deps from app/requirements.txt, NOT pyproject.toml,
# and runs `manage.py migrate` in its CMD - so a rebuild + restart is what
# applies a migration. Take a dump first (see CLAUDE.md).
# =============================================================

set -euo pipefail

DEPLOY=0
if [ "${1:-}" = "--deploy" ]; then DEPLOY=1; shift; fi

HOST="${1:-${SEMPRINI_HOST:-ubuntu@3.107.254.151}}"
SRC="$(cd "$(dirname "$0")/.." && pwd)/"
DEST="~/semprini-blog/"

EXCLUDES=(
  # host is authoritative — never push over these
  --exclude '.env.prod'
  --exclude '.env.prod.db'
  --exclude 'data/postgres18_data/'   # the live database volume
  --exclude 'data/media/'             # uploaded images, documents, narration audio
  --exclude 'data/backup/'            # host-side dumps
  --exclude 'data/static/'            # served static, written by the container
  # generated locally, rebuilt in the image
  --exclude 'data/static_collected/'
  --exclude 'app/static_collected/'
  --exclude 'app/db.sqlite3'
  # dev-only bulk
  --exclude 'examples/'
  --exclude '.venv/'
  --exclude '__pycache__/'
  --exclude '*.pyc'
  --exclude '.git/'
)

echo "→ syncing $SRC -> $HOST:$DEST"
rsync -az --info=stats2 "${EXCLUDES[@]}" "$SRC" "$HOST:$DEST" \
  | grep -E 'Number of regular files transferred|Total transferred file size' \
  | sed 's/^/  /'

if [ "$DEPLOY" -eq 0 ]; then
  echo "→ synced. To apply, run on the host:"
  echo "     cd ~/semprini-blog && docker compose build web narrator && docker compose up -d"
  exit 0
fi

echo "→ rebuilding (installs requirements.txt, runs collectstatic)"
ssh "$HOST" 'cd ~/semprini-blog && docker compose build web narrator'

echo "→ restarting (the web container migrates on start)"
ssh "$HOST" 'cd ~/semprini-blog && docker compose up -d web narrator'

echo "→ waiting for the migration and gunicorn"
ssh "$HOST" '
  for i in $(seq 1 30); do
    if docker compose -f ~/semprini-blog/docker-compose.yml logs web --tail 40 2>/dev/null \
       | grep -q "Listening at"; then echo "  up"; exit 0; fi
    sleep 2
  done
  echo "  did not report Listening at within 60s - check: docker compose logs web"
  exit 1
'
echo "→ done"
