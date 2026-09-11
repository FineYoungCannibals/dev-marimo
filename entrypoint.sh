#!/bin/sh
set -e

# Activate the virtual environment if needed.
# If the PATH is already set properly, this might be unnecessary,
# but it ensures that any activation-specific shell modifications are applied.
. "$VIRTUAL_ENV/bin/activate"

APP_DIR="/home/app_user/app"
NOTEBOOK_DIR="/home/app_user/app/notebooks"
MARIMO_CONFIG="/home/app_user/.marimo.toml"

# Prod bind-mounts .env as a file (docker-compose.prod.yml) rather than using
# Compose's env_file: directive -- Portainer's git-stack "unpacker" container
# validates env_file: paths eagerly against its own filesystem, which doesn't
# have arbitrary host paths like /opt/docker/marimo mounted, so an absolute
# env_file: path fails validation even though the file exists on the host.
# A volumes: bind-mount doesn't have that problem (resolved later by the real
# docker engine), so load it into the shell environment here instead. Dev
# uses Compose's env_file: directly (relative path, no Portainer involved),
# so this file won't exist there and the block below is a no-op.
if [ -f "$APP_DIR/.env" ]; then
  set -a
  . "$APP_DIR/.env"
  set +a
fi

# Install or update dependencies at startup.
if [ -f "$APP_DIR/pyproject.toml" ]; then
  echo "Installing/updating Python dependencies..."
  cd "$APP_DIR"
  uv sync --frozen --no-dev --no-install-project
  cd "$NOTEBOOK_DIR"  # switch back to notebook directory after installation
fi

# Refresh the lemonade model list in .marimo.toml. Best-effort: if lemonade
# is unreachable at startup, keep whatever model list is already there
# rather than blocking the container from coming up.
if [ -f "$MARIMO_CONFIG" ]; then
  echo "Refreshing lemonade model list..."
  python "$APP_DIR/scripts/refresh_ai_models.py" \
    --config "$MARIMO_CONFIG" --provider lemonade --update-chat-model \
    || echo "Warning: could not refresh lemonade models, continuing with existing config."
fi

# Execute the main command passed via CMD.
exec "$@"
