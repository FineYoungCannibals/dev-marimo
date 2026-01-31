#!/bin/sh
set -e

# Activate the virtual environment if needed.
# If the PATH is already set properly, this might be unnecessary,
# but it ensures that any activation-specific shell modifications are applied.
. "$VIRTUAL_ENV/bin/activate"

APP_DIR="/home/app_user/app"

# Install or update dependencies at startup.
if [ -f "$APP_DIR/pyproject.toml" ]; then
  echo "Installing/updating Python dependencies..."
  cd "$APP_DIR"
  uv sync --frozen --no-dev --no-install-project
fi

# Execute the main command passed via CMD.
exec "$@"
